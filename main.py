from flask import Flask, g, session, flash, request, render_template, redirect, url_for, Response
import sys
import os.path
import pprint
import time

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
from google.cloud import storage

from data import *


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
default_all_zones = ['us-central1-a', 'us-east1-b', 'us-east4-c', 'us-west1-b', 'us-west2-b']
default_machine_types = ['f1-micro', 'g1-small', 'n1-standard-2', 'n1-standard-4', 'n1-standard-8']

gwas_config = get_default_config_dict()

def get_P0_P1_ports(num_S):
    return ' '.join([str(8000 + i) for i in range(num_S)])
def get_P0_P2_ports(num_S):
    return ' '.join([str(8001 + i) for i in range(num_S)])
def get_P1_P2_ports(num_S):
    return ' '.join([str(8000 + i) for i in range(num_S)])
def get_P1_P3_ports(num_S):
    return ' '.join([str(8001 + i) for i in range(num_S)])
def get_P2_P3_ports(num_S):
    return ' '.join([str(8000 + i) for i in range(num_S)])
def get_cache_file_prefixes(num_S, role):
    return ['../cache/data{}_P{}'.format(i, role) for i in range(num_S)]


def zone_to_region(zone):
    return '-'.join(zone.split('-')[:-1])
def default_network_name(project):
    return '{}-vpc'.format(project)
def default_subnetwork_name(net_name):
    return 'sub-' + net_name


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


@app.route('/create/<string:project>', methods=['GET', 'POST'])
def create_instance(project):
    if request.method == 'POST':
        name = request.form['name']
        zone = request.form['zone']
        machine_type = request.form['machine']
        error = None

        if not name:
            error = 'Name is required.'

        if not zone:
            error = 'Zone is required.'

        if error is None:
            return redirect(url_for('setup_instance', project=project, name=name, zone=zone, machine_type=machine_type))

        flash(error)

    return render_template('create.html', all_zones=default_all_zones, all_machine_types=default_machine_types)


@app.route('/setup/<string:project>/<string:name>/<string:zone>/<string:machine_type>', methods=['GET', 'POST'])
def setup_instance(project, name, zone, machine_type):
    if request.method == 'POST':
        return redirect(url_for('choose_instance', project=project))

    # first, create VPC network if necessary
    # this logic for creating a network is not ideal, but it doesn't matter cause we're getting rid of VPC code eventually
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

        # now add a subnet
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

    # now, actually create the instance
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
                "diskSizeGb": 10
            }
        }]
    }
    compute.instances().insert(project=project, zone=zone, body=instance_body).execute()
    time.sleep(10)
    transfer_file_to_instance(project, name, 'startup.sh', '~/', delete_after=False)
    execute_shell_script_on_instance(project, name, ['chmod u+x startup.sh', './startup.sh'])

    return render_template('setup.html')


@app.route('/data/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def choose_bucket(project, zone, instance):
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
                fname = 'base-genotypes.gz'
                with open(fname, 'xb') as f:
                    client.download_blob_to_file(gen_blob, f)
                subject_ids = transform_genotype_data_vcf(fname)
                transfer_file_to_instance(project, instance, 'geno.txt', '~/secure-gwas/gwas_data/', delete_after=True)
                transfer_file_to_instance(project, instance, 'pheno.txt', '~/secure-gwas/gwas_data/', delete_after=True)
                transfer_file_to_instance(project, instance, 'pos.txt', '~/secure-gwas/gwas_data/', delete_after=False)
            
            if cov_blob:
                fname = 'base-covariates'
                with open(fname, 'xb') as f:
                    client.download_blob_to_file(cov_blob, f)
                transform_covariate_data(fname, subject_ids)
                transfer_file_to_instance(project, instance, 'cov.txt', '~/secure-gwas/gwas_data/', delete_after=True)

            return redirect(url_for('load_config', project=project, zone=zone, instance=instance))

        flash(error)

    return render_template('bucket.html', blobs=list(all_blobs.keys()))


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
            read_config_file(fname, gwas_config)

            return redirect(url_for('customize_config', project=project, zone=zone, instance=instance))

    return render_template('load_config.html')


@app.route('/customizeConfig/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def customize_config(project, zone, instance):
    if request.method == 'POST':     
        for key in request.form:
            tokens = request.form[key].split()
            update_config_dict(gwas_config, key, tokens)

        # generate the commands to update the parameter files stored on the instance
        def gen_command(search_and_replace_text_pairs, role):
            cmds = []
            for k, v in search_and_replace_text_pairs:
                cmds.append('sed -i "s|^{k}.*$|{k} {v}|g" ~/secure-gwas/par/test.par.{role}.txt'.format(k=k, v=v, role=role))
            return cmds

        num_S = gwas_config['NUM_S']
        roles = []
        if gwas_config['CP_ROLE']:
            roles.append(gwas_config['CP_ROLE'])
        if gwas_config['S_ROLE']:
            roles.apend(3)
            
        for role in roles:
            pairs = []

            # GWAS Parameters
            pairs.append(('NUM_INDS', ' '.join([str(x) for x in gwas_config['NUM_INDS']])))
            pairs.append(('NUM_SNPS', gwas_config['NUM_SNPS']))
            pairs.append(('NUM_COVS', gwas_config['NUM_COVS']))

            # IP Addresses and Ports
            if role == 0:
                pairs.append(('PORT_P0_P1', get_P0_P1_ports(num_S)))
                pairs.append(('PORT_P0_P2', get_P0_P2_ports(num_S)))
            elif role == 1:
                pairs.append(('PORT_P0_P1', get_P0_P1_ports(num_S)))
                pairs.append(('PORT_P1_P2', get_P1_P2_ports(num_S)))
                pairs.append(('PORT_P1_P3', get_P1_P3_ports(num_S)))
                pairs.append(('IP_ADDR_P0', gwas_config['IP_ADDR_P0']))
            elif role == 2:          
                pairs.append(('PORT_P0_P2', get_P0_P2_ports(num_S)))
                pairs.append(('PORT_P1_P2', get_P1_P2_ports(num_S)))
                pairs.append(('PORT_P2_P3', get_P2_P3_ports(num_S)))
                pairs.append(('IP_ADDR_P0', gwas_config['IP_ADDR_P0']))
                pairs.append(('IP_ADDR_P1', gwas_config['IP_ADDR_P1']))
            elif role == 3:
                pairs.append(('PORT_P1_P2', get_P1_P2_ports(num_S)))
                pairs.append(('PORT_P2_P3', get_P2_P3_ports(num_S)))
                pairs.append(('IP_ADDR_P1', gwas_config['IP_ADDR_P1']))
                pairs.append(('IP_ADDR_P2', gwas_config['IP_ADDR_P2']))

            # SNP Position File
            if role < 3:
                pairs.append(('SNP_POS_FILE', '../gwas_data/pos.txt'))
                pairs.append(('CACHE_FILE_PREFIX', get_cache_file_prefixes(num_S, role)))

            execute_shell_script_on_instance(project, instance, gen_command(pairs, role))

        # now create the VPC peering connections between communicating instances to allow traffic
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
        
        for other_proj in peer_gcp_projects:
            body = {
                'networkPeering': {
                    'name': 'peering-{}'.format(other_proj),
                    'network': 'https://www.googleapis.com/compute/v1/projects/{}/global/networks/{}'.format(other_proj, default_network_name(other_proj)),
                    'exchangeSubnetRoutes': True
                }
            }
            compute.networks().addPeering(project=project, network=default_network_name(project), body=body).execute()
        
        return redirect(url_for('upload_pos', project=project, zone=zone, instance=instance))

        flash(error)

    return render_template('customize_config.html', config=gwas_config, num_inds=[str(x) for x in gwas_config['NUM_INDS']])


@app.route('/pos/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def upload_pos(project, zone, instance):
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
                # should probably take union here
                transfer_file_to_instance(project, instance, fname, '~/secure-gwas/gwas_data/pos.txt', delete_after=False)
                
                return redirect(url_for('start_gwas', project=project, zone=zone, instance=instance))

        flash(error)

    return render_template('pos.html', is_S=is_S)


@app.route('/start/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def start_gwas(project, zone, instance):
    if request.method == 'POST':
        return redirect(url_for('gwas_output', project=project, zone=zone, instance=instance))

    return render_template('start.html')


# Todo: is this dead code?
# @app.route('/gwas/<string:project>/<string:zone>/<string:instance>/<int:machineid>/<int:is_S>', methods=['GET', 'POST'])
# def gwas_output(project, zone, instance, machineid, is_S):
#     if request.method == 'POST':
#         return redirect(url_for('gwas_output2', project=project, zone=zone, instance=instance,  machineid=machineid, is_S=is_S))

#     # create the commands to run the GWAS protocol
#     cmds1 = [
#         'cd ~/secure-gwas/code',
#         'bin/DataSharingClient {role} ../par/test.par.{role}.txt'.format(role=machineid),
#         'echo completed'
#     ]
#     cmds2 = [
#         'cd ~/secure-gwas/code',
#         'bin/DataSharingClient 3 ../par/test.par.3.txt ../gwas_data/'
#     ]
#     cmds3 = [
#         'cd ~/secure-gwas/code',
#         'bin/GwasClient {role} ../par/test.par.{role}.txt'.format(role=machineid),
#         'echo completed'
#     ]

#     # execute the commands on the remote machine asynchronously
#     def run_cmds():
#         # first run the DataSharing Client
#         proc2 = None
#         if machineid != 3:
#             proc = execute_shell_script_asynchronous(project, instance, cmds1)
#             if is_S:
#                 proc2 = execute_shell_script_asynchronous(project, instance, cmds2)
#         else:
#             proc = execute_shell_script_asynchronous(project, instance, cmds2)

#         print('{}: process ID is {}'.format(machineid, proc.pid))
        
#         # stream the stdout output to the webpage in real time
#         for line in iter(proc.stdout.readline, ''):
#             line_formatted = line.decode('utf-8').rstrip()
#             if line_formatted == 'completed':
#                 break
#             if len(line_formatted) > 0:
#                 yield line_formatted + '<br>\n'
#                 print('{}: {}'.format(machineid, line_formatted))

#         # kill the spawned process
#         kill_asynchronous_process(proc.pid)
#         if is_S:
#             kill_asynchronous_process(proc2.pid)

#         # then run the actual GWAS Client
#         if machineid != 3:
#             proc = execute_shell_script_asynchronous(project, instance, cmds3)
                    
#             # stream the stdout output to the webpage in real time
#             for line in iter(proc.stdout.readline, ''):
#                 line_formatted = line.decode('utf-8').rstrip()
#                 if line_formatted == 'completed':
#                     break
#                 if len(line_formatted) > 0:
#                     yield line_formatted + '<br>\n'
#                     print('{}: {}'.format(machineid, line_formatted))

#             # kill the spawned process
#             kill_asynchronous_process(proc.pid)

#     return Response(run_cmds(), mimetype='text/html')

@app.route('/gwas/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def gwas_output(project, zone, instance):
    if request.method == 'POST':
        return redirect(url_for('gwas_output2', project=project, zone=zone, instance=instance))

    # create the commands to run the GWAS protocol
    cmds1 = [
        'cd ~/secure-gwas/code',
        'bin/DataSharingClient {role} ../par/test.par.{role}.txt'.format(role=machineid),
        'echo completed'
    ]
    cmds2 = [
        'cd ~/secure-gwas/code',
        'bin/DataSharingClient 3 ../par/test.par.3.txt ../gwas_data/'
    ]

    # execute the commands on the remote machine asynchronously
    def run_cmds():
        proc2 = None
        if machineid != 3:
            proc = execute_shell_script_asynchronous(project, instance, cmds1)
            if is_S:
                proc2 = execute_shell_script_asynchronous(project, instance, cmds2)
        else:
            proc = execute_shell_script_asynchronous(project, instance, cmds2)
        
        # stream the stdout output to the webpage in real time
        for line in iter(proc.stdout.readline, ''):
            line_formatted = line.decode('utf-8').rstrip()
            if line_formatted == 'completed':
                break
            if len(line_formatted) > 0:
                yield line_formatted + '<br>\n'
                print('{}: {}'.format(machineid, line_formatted))

        # kill the spawned process
        proc.terminate()
        if is_S:
            proc2.terminate()
        # kill_asynchronous_process(proc.pid)
        # if is_S:
        #     kill_asynchronous_process(proc2.pid)

        yield '<form method="post"><input type="submit" value="Next" /></form>'

    return Response(run_cmds(), mimetype='text/html')


@app.route('/gwas2/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def gwas_output2(project, zone, instance):
     # create the commands to run the GWAS protocol
    cmds = [
        'cd ~/secure-gwas/code',
        'bin/GwasClient {role} ../par/test.par.{role}.txt'.format(role=machineid),
        'echo completed'
    ]
    
    # execute the commands on the remote machine asynchronously
    def run_cmds():
        if machineid != 3:
            proc = execute_shell_script_asynchronous(project, instance, cmds)
            
            # stream the stdout output to the webpage in real time
            for line in iter(proc.stdout.readline, ''):
                line_formatted = line.decode('utf-8').rstrip()
                if line_formatted == 'completed':
                    break
                if len(line_formatted) > 0:
                    yield line_formatted + '<br>\n'
                    print('{}: {}'.format(machineid, line_formatted))
                
    return Response(run_cmds(), mimetype='text/html')


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
