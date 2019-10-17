from flask import Flask, g, session, flash, request, render_template, redirect, url_for
import sys
import os.path
import pprint

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
from google.cloud import storage

from data import transfer_file_to_instance, execute_shell_script_on_instance, transform_genotype_data_vcf, transform_covariate_data


app = Flask(__name__)
app.config.from_mapping(SECRET_KEY='dev')


credentials = GoogleCredentials.get_application_default()
compute = discovery.build('compute', 'v1', credentials=credentials)
role_to_id = {
    'CP0': 0,
    'CP1': 1,
    'CP2': 2,
    'S': 3
}
def zone_to_region(zone):
    return '-'.join(zone.split('-')[:-1])


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
    return "<h1>Not Implemented Yet</h1>"


@app.route('/data/<string:project>/<string:zone>/<string:instance>', methods=['GET', 'POST'])
def choose_bucket(project, zone, instance):
    client = storage.Client(project=project)
    all_blobs = {}
    for bucket in client.list_buckets():
        for blob in client.list_blobs(bucket):
            if blob.name[-1] != '/':
                all_blobs[blob.name] = blob

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

            return redirect(url_for('upload_pos', project=project, zone=zone, instance=instance, is_S=is_S))

        flash(error)

    return render_template('bucket.html', blobs=list(all_blobs.keys()))


@app.route('/pos/<string:project>/<string:zone>/<string:instance>/<int:is_S>', methods=['GET', 'POST'])
def upload_pos(project, zone, instance, is_S):
    if request.method == 'POST':
        if is_S:
            return redirect(url_for('choose_role', project=project, zone=zone, instance=instance, is_S=is_S))

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
                transfer_file_to_instance(project, instance, fname, '~/secure-gwas/gwas_data/', delete_after=False)
                return redirect(url_for('choose_role', project=project, zone=zone, instance=instance, is_S=is_S))

        flash(error)

    return render_template('pos.html', is_S=is_S)


@app.route('/role/<string:project>/<string:zone>/<string:instance>/<int:is_S>', methods=['GET', 'POST'])
def choose_role(project, zone, instance, is_S):
    if request.method == 'POST':
        role = request.form['role']
        error = None
        
        if not role:
            error = "Please choose a valid role before proceeding."

        if not error:
            return redirect(url_for('load_config', project=project, zone=zone, instance=instance, machineid=role_to_id[role], is_S=is_S))
        
        flash(error)

    return render_template('role.html', is_S=is_S)


@app.route('/config/<string:project>/<string:zone>/<string:instance>/<int:machineid>/<int:is_S>', methods=['GET', 'POST'])
def load_config(project, zone, instance, machineid, is_S):
    if request.method == 'POST':
        fname = request.form['fname']
        error = None

        if not fname:
            error = 'Please enter a file path before proceeding.'

        if not fname.endswith('config.txt'):
            error = 'Please give full path to the pos.txt file, not just a path to its directory.'

        elif fname.startswith('~'):
            error = 'Please give absolute path to the pos.txt file, not a relative path.'

        elif not os.path.isfile(fname):
            error = 'Please give an absolute path to a file that exists on your local machine.'

        if error is None:
            # first, obtain external IP addresses and ports from the config file
            IP_dict = {}
            port_dict = {}
            proj_dict = {}
            with open(fname) as f:
                for i in range(4):
                    line = f.readline()
                    tokens = line.split()
                    IP_dict[tokens[0]] = tokens[1]
                for i in range(5):
                    line = f.readline()
                    tokens = line.split()
                    port_dict[tokens[0]] = tokens[1]
                for i in range(4):
                    line = f.readline()
                    tokens = line.split()
                    network_dict[i] = tokens[1]

            roles = [machineid]
            if is_S:
                roles.append(3)
            print(roles)

            # generate the command to update the ports and IP addresses on the parameter file stored on the instance
            cmds = []
            for role in roles:
                if role == 0:
                    cmds.extend([
                        'sed -i "s|^PORT_P0_P1.*$|PORT_P0_P1 {}|g" ~/secure-gwas/par/test.par.0.txt'.format(port_dict['P0_P1']),
                        'sed -i "s|^PORT_P0_P2.*$|PORT_P0_P2 {}|g" ~/secure-gwas/par/test.par.0.txt'.format(port_dict['P0_P2']),
                        'sed -i "s|^SNP_POS_FILE.*$|SNP_POS_FILE ../gwas_data/pos.txt|g" ~/secure-gwas/par/test.par.0.txt'
                    ])

                if role == 1:
                    cmds.extend([
                        'sed -i "s|^PORT_P0_P1.*$|PORT_P0_P1 {}|g" ~/secure-gwas/par/test.par.1.txt'.format(port_dict['P0_P1']),
                        'sed -i "s|^PORT_P1_P2.*$|PORT_P1_P2 {}|g" ~/secure-gwas/par/test.par.1.txt'.format(port_dict['P1_P2']),
                        'sed -i "s|^PORT_P1_P3.*$|PORT_P1_P3 {}|g" ~/secure-gwas/par/test.par.1.txt'.format(port_dict['P1_P3']),
                        'sed -i "s|^IP_ADDR_P0.*$|IP_ADDR_P0 {}|g" ~/secure-gwas/par/test.par.1.txt'.format(IP_dict['P0']),
                        'sed -i "s|^IP_ADDR_P2.*$|IP_ADDR_P2 {}|g" ~/secure-gwas/par/test.par.1.txt'.format(IP_dict['P2']),
                        'sed -i "s|^SNP_POS_FILE.*$|SNP_POS_FILE ../gwas_data/pos.txt|g" ~/secure-gwas/par/test.par.1.txt'
                    ])

                if role == 2:
                    cmds.extend([
                        'sed -i "s|^PORT_P0_P2.*$|PORT_P0_P2 {}|g" ~/secure-gwas/par/test.par.2.txt'.format(port_dict['P0_P2']),
                        'sed -i "s|^PORT_P1_P2.*$|PORT_P1_P2 {}|g" ~/secure-gwas/par/test.par.2.txt'.format(port_dict['P1_P2']),
                        'sed -i "s|^PORT_P2_P3.*$|PORT_P2_P3 {}|g" ~/secure-gwas/par/test.par.2.txt'.format(port_dict['P2_P3']),
                        'sed -i "s|^IP_ADDR_P0.*$|IP_ADDR_P0 {}|g" ~/secure-gwas/par/test.par.2.txt'.format(IP_dict['P0']),
                        'sed -i "s|^IP_ADDR_P1.*$|IP_ADDR_P1 {}|g" ~/secure-gwas/par/test.par.2.txt'.format(IP_dict['P1']),
                        'sed -i "s|^SNP_POS_FILE.*$|SNP_POS_FILE ../gwas_data/pos.txt|g" ~/secure-gwas/par/test.par.2.txt'
                    ])

                if role == 3:
                    cmds.extend([
                        'sed -i "s|^PORT_P1_P3.*$|PORT_P1_P3 {}|g" ~/secure-gwas/par/test.par.3.txt'.format(port_dict['P1_P3']),
                        'sed -i "s|^PORT_P2_P3.*$|PORT_P2_P3 {}|g" ~/secure-gwas/par/test.par.3.txt'.format(port_dict['P2_P3']),
                        'sed -i "s|^IP_ADDR_P1.*$|IP_ADDR_P1 {}|g" ~/secure-gwas/par/test.par.3.txt'.format(IP_dict['P1']),
                        'sed -i "s|^IP_ADDR_P2.*$|IP_ADDR_P2 {}|g" ~/secure-gwas/par/test.par.3.txt'.format(IP_dict['P2']),
                    ])

            execute_shell_script_on_instance(project, instance, cmds)

            # then, create a VPC network for communication, if necessary
            # existing_nets = compute.networks().list(project=project).execute()['items']
            # for role in roles:
            #     need_to_create = True
            #     for net in existing_nets:
            #         if net['name'] == 'net-p{}'.format(role):
            #             need_to_create = False
            #     if need_to_create:
            #         req_body = {
            #             'name': 'net-p{}'.format(role),
            #             'autoCreateSubnetworks': False,
            #             'routingConfig': {'routingMode': 'REGIONAL'}
            #         }
            #         compute.networks().insert(project=project, body=req_body).execute()

            #         # now add a subnet
            #         # add 30 second delay cause it takes time to create a network
            #         nets = compute.networks().list(project=project).execute()['items']
            #         for net in nets:
            #             if net['name'] == 'net-p{}'.format(role):
            #                 network_url = net['selfLink']
            #         req_body = {
            #             'name': 'sub-p{}'.format(role),
            #             'network': network_url,
            #             'ipCidrRange': '10.0.{}.0/24'.format(role),
            #             'region': zone_to_region(zone)
            #         }
            #         compute.subnetworks().insert(project=project, region=zone_to_region(zone), body=req_body).execute()

            # now create the VPC peering connections between communicating instances to allow traffic
            for role in roles:
                if role == 0:
                    connect_roles = [1, 2]
                elif role == 1:
                    connect_roles = [0, 2, 3]
                elif role == 2:
                    connect_roles = [0, 1, 3]
                else:
                    connect_roles = [1, 2]

                for other in connect_roles:
                    body = {
                        'networkPeering': {
                            'name': 'peer-p{}-p{}'.format(role, other),
                            'network': 'https://www.googleapis.com/compute/v1/projects/{}/global/networks/net-p{}'.format(network_dict[other], other),
                            'exchangeSubnetRoutes': True
                        }
                    }
                    compute.networks().addPeering(project=project, network='net-p{}'.format(role), body=body).execute()
            
            # return redirect(url_for('choose_role', project=project, zone=zone, instance=instance, is_S=is_S))

        flash(error)

    return render_template('config.html', is_S=is_S)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
