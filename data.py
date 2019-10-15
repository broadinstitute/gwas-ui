import numpy as np
import pandas as pd
import os

def transfer_file_to_instance(project, instance, fname, path, delete_after=False):
	if path[-1] != '/':
		path += '/'
	cmd = 'gcloud compute scp --project "{}" {} {}:{}'.format(project, fname, instance, path)
	os.system(cmd)

	if delete_after:
		os.remove(fname)

def transform_covariate_data(fname):
	df = pd.read_csv(fname, delimiter='\t', encoding='utf-8')[['Sex', 'Population code']]
	df1 = df['Sex'].replace(['female', 'male'], [0, 1])
	df2 = pd.get_dummies(df['Population code'])
	df_final = pd.concat([df1, df2], axis=1)
	np.savetxt('cov.txt', df_final.to_numpy().astype(int), fmt='%i')
	os.remove(fname)
