from flask import Flask, g, session, flash, request, render_template, redirect, url_for, Response
import sys
import os.path
import pprint
import time

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
from google.cloud import storage

from data import *


# This file contains all the endpoints for the secure GWAS UI


app = Flask(__name__)
app.config.from_mapping(SECRET_KEY='dev')

# Global Variables
credentials = GoogleCredentials.get_application_default()
compute = discovery.build('compute', 'v1', credentials=credentials)
role_to_id = {
    'CP0': 0,
    'CP1': 1,
    'CP2': 2,
    'S': 3
}
# To Do: Expand these default options (used during instance creation) to give users more flexibility over their
# configured GWAS instance
default_all_zones = [('us-central1-a', '   (Iowa)'), ('us-east1-b', '   (South Carolina)'), ('us-east4-c', '   (Northern Virgina)'),
                    ('us-west1-b', '   (Oregon)'), ('us-west2-b', '   (Los Angeles)')]
default_machine_types = [('g1-small', '   (1 vCPU, 1.7 GB RAM)'), ('n1-standard-1', '   (1 vCPU, 3.75 GB RAM)'),
                        ('n1-standard-4', '   (4 vCPU, 15 GB RAM)'), ('n1-standard-32', '   (32 vCPU, 120 GB RAM)'),
                        ('n1-highcpu-32', '   (32 vCPU, 28.8 GB RAM)')]

# The all_gwas_configs dictionary contains a mapping from a user's selected Google Cloud project and instance IDs 
# to the config dictionary that stores their GWAS parameter values
# The config dictionary is used to 
all_gwas_configs = {}
def add_gwas_config(project, instance):
    new_config = get_default_config_dict()
    all_gwas_configs[project + instance] = new_config
    return new_config
def get_gwas_config(project, instance):
    return all_gwas_configs[project + instance]

# Simple helper functions to generate a series of non-overlapping port numbers used for inter-party GWAS communication
# Since every dataset needs at least 5 ports (corresponding to the 5 channels CP0-CP1, CP0-CP2, CP1-CP2, CP1-SP, CP2-SP),
# and since the GWAS code uses different ports for communication between different threads, we need to space out the ports
# for 2 consecutive datasets by at at least 5 * num_threads
def get_P0_P1_ports(num_S, num_threads):
    return ' '.join([str(8000 + 5 * num_threads * i) for i in range(num_S)])
def get_P0_P2_ports(num_S, num_threads):
    return ' '.join([str(8001 + 5 * num_threads * i) for i in range(num_S)])
def get_P1_P2_ports(num_S, num_threads):
    return ' '.join([str(8002 + 5 * num_threads * i) for i in range(num_S)])
def get_P1_P3_ports(num_S, num_threads):
    return ' '.join([str(8003 + 5 * num_threads * i) for i in range(num_S)])
def get_P2_P3_ports(num_S, num_threads):
    return ' '.join([str(8004 + 5 * num_threads * i) for i in range(num_S)])

# Simple helper function to generate a series of cache file prefixes corresponding to the different GWAS datasets
# These cache file prefixes are used to locate the directory where all GWAS secret-shared and intermediate data is written
def get_cache_file_prefixes(num_S, role):
    return ' '.join(['../cache/data{}_P{}'.format(i, role) for i in range(num_S)])

# Helper functions for Google Cloud specific behavior
# The default network/subnetwork names are based on GWAS-specific conventions
def zone_to_region(zone):
    return '-'.join(zone.split('-')[:-1])
def default_network_name(project):
    return '{}-vpc'.format(project)
def default_subnetwork_name(net_name):
    return 'sub-' + net_name


# Entry point into the GWAS UI, which asks user to simply enter the name of their cloud project
@app.route('/', methods=('GET', 'POST'))
def choose_project():
    if request.method == 'POST':
        project = request.form['project']
        error = None

        if not project:
            error = 'Project is required.'

        if error is None:
            return redirect(url_for('choose_instance', project=project))

        flash(error)

    return render_template('project.html')


# Endpoint that allows user to choose the specific cloud instance they want to use for this GWAS study
# Also has an option for users to configure a new GWAS instance
@app.route('/instance/<string:project>', methods=['GET', 'POST'])
def choose_instance(project):
    if request.method == 'POST':
        instance = request.form['instance']
        error = None

        if not instance:
            error = 'Instance is required.'

        if error is None:
            instance, zone = instance.split(',')

            # actually start the instance
            compute.instances().start(project=project, zone=zone, instance=instance).execute()

            return redirect(url_for('choose_bucket', project=project, zone=zone, instance=instance))

        flash(error)

    # generate a list of all existing instances within this project
    all_instances = []
    try:
        response = compute.zones().list(project=project).execute()
        all_zones = response['items'] if 'items' in response else []
        for zone in all_zones:
            new_response = compute.instances().list(
                project=project, zone=zone['name']).execute()
            instances = new_response['items'] if 'items' in new_response else []
            for instance in instances:
                all_instances.append((instance['name'], zone['name']))
        return render_template('instance.html', project=project, instances=all_instances)
    
    except:
        flash('Input a valid Google Cloud project id.')
        return redirect(url_for('choose_project'))


# Endpoint that allows users to create a new GWAS-configured instance based on their desired specifications
@app.route('/create/<string:project>', methods=['GET', 'POST'])
def create_instance(project):
    if request.method == 'POST':
        name = request.form['name']
        zone = request.form['zone']
        machine_type = request.form['machine']
        storage = request.form['storage']
        error = None

        if not name:
            error = 'Name is required.'

        if not zone:
            error = 'Zone is required.'

        if not machine_type:
            error = 'Machine type is required'

        if not storage:
            error = 'Storage is required'

        if error is None:
            return redirect(url_for('setup_instance', project=project, name=name, zone=zone, machine_type=machine_type, disk_size=int(storage)))

        flash(error)

    return render_template('create.html', all_zones=default_all_zones, all_machine_types=default_machine_types)


# After the user has entered their desired specifications for a new GWAS instance, the UI navigates to this success page
# In the background, this endpoint actually sets up the GWAS network, creates the new instance, and installs the
# necessary packages to run GWAS code
@app.route('/setup/<string:project>/<string:name>/<string:zone>/<string:machine_type>/<int:disk_size>', methods=['GET', 'POST'])
def setup_instance(project, name, zone, machine_type, disk_size):
    if request.method == 'POST':
        return redirect(url_for('choose_instance', project=project))

    # first, create a private GWAS-specific VPC network if necessary
    net_name = default_network_name(project)
    existing_nets = compute.networks().list(project=project).execute()['items']
    need_to_create = True
    for net in existing_nets:
        if net['name'] == net_name:
            need_to_create = False
    if need_to_create:
        print('creating network')
        req_body = {
            'name': net_name,
            'autoCreateSubnetworks': False,
            'routingConfig': {'routingMode': 'GLOBAL'}
        }
        compute.networks().insert(project=project, body=req_body).execute()

        # now add a subnet to this VPC network
        # add 30 second delay cause it takes time to create a network
        time.sleep(30)
        nets = compute.networks().list(project=project).execute()['items']
        network_url = ''
        for net in nets:
            if net['name'] == net_name:
                network_url = net['selfLink']
        req_body = {
            'name': default_subnetwork_name(net_name),
            'network': network_url,
            'ipCidrRange': '10.{}.{}.0/24'.format(random.randint(0, 255), random.randint(0, 255)), 
            'region': zone_to_region(zone)
        }
        compute.subnetworks().insert(project=project, region=zone_to_region(zone), body=req_body).execute()

        # finally, add a firewall rule allowing ingress
        firewall_body = {
            'name': 'vpc-allow-ingress',
            'network': network_url,
            'priority': 1000,
            'sourceRanges': ['0.0.0.0/0'],
            'allowed': [{'IPProtocol': 'all'}]
        }
        compute.firewalls().insert(project=project, body=firewall_body).execute()

    # now, actually create the instance and attach it to this GWAS network
    instance_body = {
        "name": name,
        "machineType": "zones/{}/machineTypes/{}".format(zone, machine_type),
        "networkInterfaces": [{
            "subnetwork": "regions/{}/subnetworks/{}".format(zone_to_region(zone), default_subnetwork_name(net_name))
        }],
        "disks": [{
            "boot": True,
            "initializeParams": {
                "sourceImage": "projects/debian-cloud/global/images/family/debian-9",
                "diskType": "zones/{}/diskTypes/pd-ssd".format(zone),
                "diskSizeGb": disk_size
            }
        }]
    }
    compute.instances().insert(project=project, zone=zone, body=instance_body).execute()
    time.sleep(10)

    # setup the new GWAS instnace with the necessary packages and codebase using a startup shell script
    transfer_file_to_instance(project, name, 'startup.sh', '~/', delete_after=False)
    execute_shell_script_on_instance(project, name, ['chmod u+x startup.sh', './startup.sh'])

    return render_template('setup.html')


# This endpoint allows users to specify a cloud storage bucket that contains the input data for GWAS
@app.route('/data/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def choose_bucket(project, zone, instance):
    # first, generate a flattened view of all storage blobs in this project
    client = storage.Client(project=project)
    all_blobs = {}
    for bucket in client.list_buckets():
        try: 
            for blob in client.list_blobs(bucket):
                if blob.name[-1] != '/':
                    all_blobs[blob.name] = blob
        except:
            continue

    if request.method == 'POST':
        gen_key = request.form['gen_blob']
        cov_key = request.form['cov_blob']
        error = None

        if not gen_key or not cov_key:
            error = "Please choose your data sources before proceeding. If you are not playing the role of S, simply choose 'No Input Data'"

        if not error:
            gen_blob = all_blobs[gen_key] if (gen_key != 'None' and gen_key != 'Done') else None
            cov_blob = all_blobs[cov_key] if (cov_key != 'None' and cov_key != 'Done') else None

            is_S = (gen_blob is not None) or (gen_key == 'Done')

            subject_ids = None
            if gen_blob:
                # if user specifies genotype data, convert it from VCF to text file format
                # then transfer the data to compute instance
                fname = 'base-genotypes.gz'
                with open(fname, 'xb') as f:
                    client.download_blob_to_file(gen_blob, f)
                subject_ids = transform_genotype_data_vcf(fname)
                transfer_file_to_instance(project, instance, 'geno.txt', '~/secure-gwas/gwas_data/', delete_after=True)
                transfer_file_to_instance(project, instance, 'pheno.txt', '~/secure-gwas/gwas_data/', delete_after=True)
                transfer_file_to_instance(project, instance, 'pos.txt', '~/secure-gwas/gwas_data/', delete_after=False)
            
            if cov_blob:
                # if user specifies covariate data, convert it from VCF to text file format
                # then transfer the data to compute instance
                fname = 'base-covariates'
                with open(fname, 'xb') as f:
                    client.download_blob_to_file(cov_blob, f)
                transform_covariate_data(fname, subject_ids)
                transfer_file_to_instance(project, instance, 'cov.txt', '~/secure-gwas/gwas_data/', delete_after=True)

            return redirect(url_for('load_config', project=project, zone=zone, instance=instance))

        flash(error)

    return render_template('bucket.html', blobs=list(all_blobs.keys())[:5])


# This endpoint allows users to input the location of a shared config.txt file
# This file contains settings for all GWAS parameters shared across parties, and should be
# generated by the parties independently of this UI (although we provide a template file)
@app.route('/config/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def load_config(project, zone, instance):
    if request.method == 'POST':
        fname = request.form['fname']
        error = None

        if not fname:
            error = 'Please enter a file path before proceeding.'

        if not fname.endswith('config.txt'):
            error = 'Please give full path to the config.txt file, not just a path to its directory.'

        elif fname.startswith('~'):
            error = 'Please give absolute path to the config.txt file, not a relative path.'

        elif not os.path.isfile(fname):
            error = 'Please give an absolute path to a file that exists on your local machine.'

        if error is None:
            gwas_config = add_gwas_config(project, instance)
            read_config_file(fname, gwas_config)

            return redirect(url_for('customize_config', project=project, zone=zone, instance=instance))

    return render_template('load_config.html')


# Once the user provides the config.txt file location, the UI loads the data and displays it in an editable
# text form view to the user, so they can review and finalize all settings before proceeding
@app.route('/customizeConfig/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def customize_config(project, zone, instance):
    # get the gwas config dictionary for this user
    gwas_config = get_gwas_config(project, instance)

    if request.method == 'POST':
        error = None

        if gwas_config['S_ROLE'] is not None and (gwas_config['S_ROLE'] < 0 or gwas_config['S_ROLE'] >= gwas_config['NUM_S']):
            error = "Make sure that the S role is a number between 0 and Num_S - 1"

        if error is None:
            # first, update the gwas config dictionary with any updated settings 
            for key in request.form:
                tokens = request.form[key].split()
                update_config_dict(gwas_config, key, tokens)

            print("Is acting as S: {}".format(gwas_config['S_ROLE'] is not None))
            
            # generate the commands to update the parameter files that are actually stored on the instance
            def gen_command(search_and_replace_text_pairs, role):
                cmds = []
                for k, v in search_and_replace_text_pairs:
                    cmds.append('sed -i "s|^{k}.*$|{k} {v}|g" ~/secure-gwas/par/test.par.{role}.txt'.format(k=k, v=v, role=role))
                return cmds

            num_S = gwas_config['NUM_S']
            roles = []
            if gwas_config['CP_ROLE'] is not None:
                roles.append(gwas_config['CP_ROLE'])
            if gwas_config['S_ROLE']is not None:
                roles.append(3)

            print("All machine IDs for this server: {}".format(roles))
                
            # for each role (CP0, CP1, CP2, S) that this user is enacting, update their corresponding GWAS parameter file
            # to do this, we first generate a list of parameter key-value pairs
            for role in roles:
                pairs = []

                # GWAS Parameters
                pairs.append(('NUM_INDS', ' '.join([str(x) for x in gwas_config['NUM_INDS']])))
                pairs.append(('NUM_SNPS', gwas_config['NUM_SNPS']))
                pairs.append(('NUM_COVS', gwas_config['NUM_COVS']))
                pairs.append(('NUM_CHUNKS', ' '.join([str(x) for x in gwas_config['NUM_CHUNKS']])))
                pairs.append(('NUM_THREADS', gwas_config['NUM_THREADS']))
                pairs.append(('NTL_NUM_THREADS', gwas_config['NTL_NUM_THREADS']))

                # IP Addresses and Ports
                if role == 0:
                    pairs.append(('PORT_P0_P1', get_P0_P1_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('PORT_P0_P2', get_P0_P2_ports(num_S, gwas_config['NUM_THREADS'])))
                elif role == 1:
                    pairs.append(('PORT_P0_P1', get_P0_P1_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('PORT_P1_P2', get_P1_P2_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('PORT_P1_P3', get_P1_P3_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('IP_ADDR_P0', gwas_config['IP_ADDR_P0']))
                elif role == 2:          
                    pairs.append(('PORT_P0_P2', get_P0_P2_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('PORT_P1_P2', get_P1_P2_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('PORT_P2_P3', get_P2_P3_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('IP_ADDR_P0', gwas_config['IP_ADDR_P0']))
                    pairs.append(('IP_ADDR_P1', gwas_config['IP_ADDR_P1']))
                elif role == 3:
                    pairs.append(('PORT_P1_P2', get_P1_P2_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('PORT_P2_P3', get_P2_P3_ports(num_S, gwas_config['NUM_THREADS'])))
                    pairs.append(('IP_ADDR_P1', gwas_config['IP_ADDR_P1']))
                    pairs.append(('IP_ADDR_P2', gwas_config['IP_ADDR_P2']))

                # Filenames
                if role < 3:
                    pairs.append(('SNP_POS_FILE', '../gwas_data/pos.txt'))
                    pairs.append(('CACHE_FILE_PREFIX', get_cache_file_prefixes(num_S, role)))

                # we then execute shell commands on the compute instance to edit the parameter file
                execute_shell_script_on_instance(project, instance, gen_command(pairs, role))

            # now create the VPC peering connections between communicating instances
            # this allows instances in distinct projects/networks to communicate freely with each other
            peer_gcp_projects = set([])
            for role in roles:
                if role == 0:
                    peer_gcp_projects.add(gwas_config['PROJ1'])
                    peer_gcp_projects.add(gwas_config['PROJ2'])
                elif role == 1:
                    peer_gcp_projects.add(gwas_config['PROJ0'])
                    peer_gcp_projects.add(gwas_config['PROJ2'])
                    for proj in gwas_config['PROJ3']:
                        peer_gcp_projects.add(proj)
                elif role == 2:
                    peer_gcp_projects.add(gwas_config['PROJ0'])
                    peer_gcp_projects.add(gwas_config['PROJ1'])
                    for proj in gwas_config['PROJ3']:
                        peer_gcp_projects.add(proj)
                else:
                    peer_gcp_projects.add(gwas_config['PROJ0'])
                    peer_gcp_projects.add(gwas_config['PROJ2'])

            # remove your own project, since networks shouldn't peer with themselves
            if project in peer_gcp_projects:
                peer_gcp_projects.remove(project)

            # remove all projects that have already been peered to
            network_info = compute.networks().get(project=project, network=default_network_name(project)).execute()
            if 'peerings' in network_info:
                for peering in network_info['peerings']:
                    project_name = peering['name'].replace('peering-', '')
                    if project_name in peer_gcp_projects:
                        peer_gcp_projects.remove(project_name)

            print(peer_gcp_projects)
            
            for other_proj in peer_gcp_projects:
                body = {
                    'networkPeering': {
                        'name': 'peering-{}'.format(other_proj),
                        'network': 'https://www.googleapis.com/compute/v1/projects/{}/global/networks/{}'.format(other_proj, default_network_name(other_proj)),
                        'exchangeSubnetRoutes': True
                    }
                }
                compute.networks().addPeering(project=project, network=default_network_name(project), body=body).execute()
                time.sleep(20) # need delay between successive operations
            
            return redirect(url_for('upload_pos', project=project, zone=zone, instance=instance))

        flash(error)

    return render_template('customize_config.html', config=gwas_config, num_inds=[str(x) for x in gwas_config['NUM_INDS']], 
                            num_chunks=[str(x) for x in gwas_config['NUM_CHUNKS']])


# This endpoint allows CPs to upload the pos.txt file that they need to run GWAS to their compute instnace
# They should receive this pos.txt file from SP, although the logic for this is left outside of the codebase
@app.route('/pos/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def upload_pos(project, zone, instance):
    gwas_config = get_gwas_config(project, instance)
    is_S = gwas_config['S_ROLE'] is not None

    if request.method == 'POST':
        if is_S:
            return redirect(url_for('start_gwas', project=project, zone=zone, instance=instance))

        else:
            fname = request.form['fname']
            error = None

            if not fname:
                error = 'Please enter a file path before proceeding.'

            if not fname.endswith('pos.txt'):
                error = 'Please give full path to the pos.txt file, not just a path to its directory.'

            elif fname.startswith('~'):
                error = 'Please give absolute path to the pos.txt file, not a relative path.'

            elif not os.path.isfile(fname):
                error = 'Please give an absolute path to a file that exists on your local machine.'

            if error is None:
                # To Do: should probably take union of all inputted pos.txt files across datasets/SPs here
                # for now, we assume all SPs use the same set of genotypes, so all pos.txt files are identical
                transfer_file_to_instance(project, instance, fname, '~/secure-gwas/gwas_data/pos.txt', delete_after=False)
                
                return redirect(url_for('start_gwas', project=project, zone=zone, instance=instance))

        flash(error)

    return render_template('pos.html', is_S=is_S)


# This endpoint is the entry point for users to actually begin running the GWAS protocol
@app.route('/start/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def start_gwas(project, zone, instance):
    if request.method == 'POST':
        return redirect(url_for('gwas_output', project=project, zone=zone, instance=instance))

    return render_template('start.html')


# This endpoint takes care of the logic for running the Data Sharing Protocol on cloud instances
@app.route('/gwas/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def gwas_output(project, zone, instance):
    if request.method == 'POST':
        return redirect(url_for('gwas_output2', project=project, zone=zone, instance=instance))

    gwas_config = get_gwas_config(project, instance)
    all_cmds = []

    if gwas_config['S_ROLE'] is not None:
        all_cmds.append([
            'cd ~/secure-gwas/code',
            'bin/DataSharingClient 3 ../par/test.par.3.txt {} ../gwas_data'.format(gwas_config['S_ROLE']),
            'echo completed'
        ])
    if gwas_config['CP_ROLE']is not None:
        for i in range(gwas_config['NUM_S']):
            all_cmds.append([
                'cd ~/secure-gwas/code',
                'bin/DataSharingClient {role} ../par/test.par.{role}.txt {round}'.format(role=gwas_config['CP_ROLE'], round=i),
                'echo completed'
            ])

    # function for executing commands on the remote machine asynchronously and writing the standard out to the UI
    def run_cmds():
        procs = []
        for cmd in all_cmds:
            procs.append(execute_shell_script_asynchronous(project, instance, cmd))
        
        # stream the stdout output for just the first process to the webpage in real time
        for line in iter(procs[0].stdout.readline, ''):
            line_formatted = line.decode('utf-8').rstrip()
            if line_formatted == 'completed':
                break
            if len(line_formatted) > 0:
                yield line_formatted + '<br>\n'
                print(line_formatted)

        # kill the spawned processes
        for proc in procs:
            proc.terminate()
            # kill_asynchronous_process(proc.pid)

        yield '<form method="post"><input type="submit" value="Next" /></form>'

    return Response(run_cmds(), mimetype='text/html')


# This endpoint takes care of the logic for running the GWAS Protocol on cloud instances
@app.route('/gwas2/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def gwas_output2(project, zone, instance):
    gwas_config = get_gwas_config(project, instance)
    if gwas_config['CP_ROLE'] is not None: 
        # create the commands to run the GWAS protocol
        cmds = [
            'cd ~/secure-gwas/code',
            'bin/GwasClient {role} ../par/test.par.{role}.txt'.format(role=gwas_config['CP_ROLE']),
            'echo completed'
        ]
        
        # execute the commands on the remote machine asynchronously and write standard out to the UI
        def run_cmds():
            proc = execute_shell_script_asynchronous(project, instance, cmds)
            
            # stream the stdout output to the webpage in real time
            for line in iter(proc.stdout.readline, ''):
                line_formatted = line.decode('utf-8').rstrip()
                if line_formatted == 'completed':
                    yield '<h>Completed GWAS Protocol Successfully!</h>'
                    break
                if len(line_formatted) > 0:
                    yield line_formatted + '<br>\n'
                    print('{}: {}'.format(gwas_config['CP_ROLE'], line_formatted))
                    
        return Response(run_cmds(), mimetype='text/html')

    else:
        return '<h>Completed Data Sharing Protocol Successfully!</h>'


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
