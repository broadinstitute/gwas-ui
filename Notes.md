1. Setup
pip3 install -r requirements.txt

2. Authentication
Each user should download gcloud command line SDK to their machine, and give themselves Compute Admin and Storage Admin roles on IAM

Each user should run `gcloud auth application-default login` in their shell to temporarily set their personal user credentials as the app default credentials for API access. After this step, running the demo locally willl allow them to authenticate immediately using GoogleCredentials.

Each user should also make themselves a Storage Admin for the project using the IAM page.


Questions
1) Double check logic of generating phenotype
2) How does a research lab configure/agree upon GWAS parameters with another research lab? What is the user flow like for this step? Snags with key generation in particular?

Biggest To-Do's Remaining:
1) Add workflow for "Create New GWAS Instance" option.
2) Workflow for generating and sharing keys? Assume already done?
3) If many parties are running the role of S, just have all IP addresses separated by whitespace in the same line of config.txt, and we can run the protocol one time for each IP address.