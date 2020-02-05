import os
import random
import subprocess

import psutil
import numpy as np
import pandas as pd


# Schema for the config file used to initialize GWAS MPC protocol
def get_default_config_dict():
	return {
	    'IP_ADDR_P0': '',
	    'IP_ADDR_P1': '',
	    'IP_ADDR_P2': '',
	    'NUM_S': 1,
	    'CP_ROLE': None,
	    'S_ROLE': None,
	    'PROJ0': '',
	    'PROJ1': '',
	    'PROJ2': '',
	    'PROJ3': [''],
	    'NUM_INDS': [0],
	    'NUM_SNPS': 0,
	    'NUM_COVS': 0
	}


def update_config_dict(config_dict, kw, tokens):
	# Case 1: string value parameters
	if kw in ['IP_ADDR_P0', 'IP_ADDR_P1', 'IP_ADDR_P2', 'PROJ0', 'PROJ1', 'PROJ2']:
		if len(tokens) > 0:
			config_dict[kw] = tokens[0]

	# Case 2: integer value parameters
	elif kw in ['NUM_S', 'CP_ROLE', 'S_ROLE', 'NUM_SNPS', 'NUM_COVS']:
		if len(tokens) > 0:
			config_dict[kw] = int(tokens[0])
		else:
			config_dict[kw] = None

	# Case 3: list of string values
	elif kw in ['PROJ3']:
		config_dict[kw] = tokens

	# Case 4: list of integer values
	elif kw in ['NUM_INDS']:
		config_dict[kw] = [int(x) for x in tokens]


# Turn config file inputted by user into a dictionary fitting above schema
def read_config_file(fname, config_dict):
	with open(fname, 'r') as f:
		for line in f:
			tokens = line.split()
			kw = tokens[0]

			update_config_dict(config_dict, kw, tokens[1:])


def transfer_file_to_instance(project, instance, fname, path, delete_after=False):
	if path[-1] != '/':
		path += '/'
	cmd = 'gcloud compute scp --project {} "{}" {}:{}'.format(project, fname, instance, path)
	os.system(cmd)

	if delete_after:
		os.remove(fname)


def execute_shell_script_on_instance(project, instance, cmds):
	cmd = '; '.join(cmds)
	script = 'gcloud compute ssh {} --project {} --command \'{}\''.format(instance, project, cmd)
	os.system(script)


def execute_shell_script_asynchronous(project, instance, cmds):
	cmd = '; '.join(cmds)
	script = 'gcloud compute ssh {} --project {} --command \'{}\''.format(instance, project, cmd)
	return subprocess.Popen(script, shell=True, stdout=subprocess.PIPE)


def kill_asynchronous_process(pid):
    process = psutil.Process(pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


def transform_genotype_data_vcf(fname):
	# transforms a genotype of the form 0|1 into a genotype of the form 1
	def genotype_mapper(gen):
		alleles = gen.split('|')
		if (alleles[0] != '0' and alleles[0] != '1') or (alleles[1] != '0' and alleles[1] != '1'):
			return -1
		else:
			return int(alleles[0]) + int(alleles[1])

	# decompress VCF file
	cmd = 'gunzip -d {}'.format(fname)
	os.system(cmd)
	fname = fname[:-3]

	columns = []
	offset_index = 0
	head_index = 0

	# then, find header of file
	with open(fname, 'r') as f:
		line = f.readline()
		
		while line:
			if line[0] == '#' and line[1] != '#':
				columns = line.split()
				for i in range(len(columns)):
					if any(s.isdigit() for s in columns[i]):
						offset_index = i
						break
				break

			head_index += 1
			line = f.readline()

	# now, read the file starting from header
	df = pd.read_csv(fname, delimiter='\t', encoding='utf-8', skiprows=head_index, nrows=10000)

	# TODO: Eventually remove this
	# subsample the data to make for fast computation - only want 1000 snps
	sampled = df.sample(1000)

	# create the position data by reading first 2 columns
	position_columns = columns[:2]
	df_position = sampled[position_columns]
	np.savetxt('pos.txt', df_position.to_numpy().astype(int), fmt='%i')

	# now create the genotype data
	subject_columns = columns[offset_index:]
	genotype_data = sampled[subject_columns].to_numpy()
	genotype_data = genotype_data.transpose()
	genotype_data_final = np.vectorize(genotype_mapper)(genotype_data)
	np.savetxt('geno.txt', genotype_data_final.astype(int), fmt='%i')

	# finally, simulate the phenotype data
	snp_indices = random.sample(range(genotype_data_final.shape[1]), 10)
	weights = np.array([random.uniform(-0.1, 0.1) for _ in range(10)])
	weighted_sum = np.sum(np.multiply(genotype_data_final[:, snp_indices], weights), axis=1)
	noise = np.array([random.uniform(-1, 1) for _ in range(genotype_data_final.shape[0])])
	phenotypes = 1.0 / (1 + np.exp(-1 * (weighted_sum + noise)))
	phenotypes = np.where(phenotypes >= 0.5, np.ones(phenotypes.shape), np.zeros(phenotypes.shape))
	phenotype_data = phenotypes.transpose()
	np.savetxt('pheno.txt', phenotype_data.astype(int), fmt='%i')

	# delete the file
	os.remove(fname)

	# return the list of subjects
	return columns[offset_index:]


def transform_covariate_data(fname, ids):
	df = pd.read_csv(fname, delimiter='\t', encoding='utf-8')[['Sample name', 'Sex', 'Population code']]

	# if we need to filter down the subject ids, do that
	if ids is not None:
		df_filter = pd.DataFrame(ids, columns=['Sample name'])
		df_joined = pd.merge(df, df_filter, on='Sample name', how='inner')
	else:
		df_joined = df

	# turn gender into a 0/1 encoding
	df1 = df_joined['Sex'].replace(['female', 'male'], [0, 1])

	# turn population into a 1-hot encoding
	df2 = pd.get_dummies(df_joined['Population code'])

	# join and save the file
	df_final = pd.concat([df1, df2], axis=1)
	np.savetxt('cov.txt', df_final.to_numpy().astype(int), fmt='%i')
	os.remove(fname)
