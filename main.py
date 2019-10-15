from flask import Flask, g, session, flash, request, render_template, redirect, url_for
import sys
import pprint

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials

app = Flask(__name__)
app.config.from_mapping(SECRET_KEY='dev')

credentials = GoogleCredentials.get_application_default()
compute = discovery.build('compute', 'v1', credentials=credentials)
CERTS = None
AUDIENCE = None


def certs():
    """Returns a dictionary of current Google public key certificates for
    validating Google-signed JWTs. Since these change rarely, the result
    is cached on first request for faster subsequent responses.
    """
    import requests

    global CERTS
    if CERTS is None:
        response = requests.get(
            'https://www.gstatic.com/iap/verify/public_key'
        )
        CERTS = response.json()
    return CERTS


def get_metadata(item_name):
    """Returns a string with the project metadata value for the item_name.
    See https://cloud.google.com/compute/docs/storing-retrieving-metadata for
    possible item_name values.
    """
    import requests

    endpoint = 'http://metadata.google.internal'
    path = '/computeMetadata/v1/project/'
    path += item_name
    response = requests.get(
        '{}{}'.format(endpoint, path),
        headers={'Metadata-Flavor': 'Google'}
    )
    metadata = response.text
    return metadata


def audience():
    """Returns the audience value (the JWT 'aud' property) for the current
    running instance. Since this involves a metadata lookup, the result is
    cached when first requested for faster future responses.
    """
    global AUDIENCE
    if AUDIENCE is None:
        project_number = get_metadata('numeric-project-id')
        project_id = get_metadata('project-id')
        AUDIENCE = '/projects/{}/apps/{}'.format(
            project_number, project_id
        )
    return AUDIENCE


def validate_assertion(assertion):
    """Checks that the JWT assertion is valid (properly signed, for the
    correct audience) and if so, returns strings for the requesting user's
    email and a persistent user ID. If not valid, returns None for each field.
    """
    from jose import jwt

    try:
        info = jwt.decode(
            assertion,
            certs(),
            algorithms=['ES256'],
            audience=audience()
        )
        return info['email'], info['sub']
    except Exception as e:
        print('Failed to validate assertion: {}'.format(e), file=sys.stderr)
        return None, None


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
        print(instance)
        tokens = instance.split(',')
        return redirect(url_for('input_data', project=project, zone=tokens[1], instance=tokens[0]))

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
def input_data(project, zone, instance):
    return "<h1>Test: {}, {}, {}</h1>".format(project, zone, instance)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
