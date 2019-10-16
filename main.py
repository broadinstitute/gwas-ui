from flask import Flask, g, session, flash, request, render_template, redirect, url_for
import sys
import pprint

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
from google.cloud import storage

from data import transfer_file_to_instance, transform_genotype_data_vcf, transform_covariate_data


app = Flask(__name__)
app.config.from_mapping(SECRET_KEY='dev')
credentials = GoogleCredentials.get_application_default()
compute = discovery.build('compute', 'v1', credentials=credentials)


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
    # from flask import request
    # assertion = request.headers.get('X-Goog-IAP-JWT-Assertion')
    # email, id = validate_assertion(assertion)
    # page = "<h1>Hello {}</h1>".format(email)

    # return page
    if request.method == 'POST':
        instance = request.form['instance']
        instance, zone = instance.split(',')

        # actually start the instance
        compute.instances().start(project=project, zone=zone, instance=instance).execute()
        
        return redirect(url_for('choose_bucket', project=project, zone=zone, instance=instance))

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
        gen_blob = all_blobs[gen_key] if gen_key != 'None' else None
        cov_key = request.form['cov_blob']
        cov_blob = all_blobs[cov_key] if cov_key != 'None' else None

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
            transfer_file_to_instance(project, instance, 'cov.txt', '~/secure-gwas/gwas_data/', delete_after=False)

        # call next endpoint, passing an extra boolean to signify whether this is S or not

    return render_template('bucket.html', blobs=list(all_blobs.keys()))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
