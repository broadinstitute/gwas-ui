1. Setup
pip3 install -r requirements.txt

2. Authentication
Each user should download gcloud command line SDK to their machine, and give themselves Compute Admin and Storage Admin roles on IAM

Each user should run `gcloud auth application-default login` in their shell to temporarily set their personal user credentials as the app default credentials for API access. After this step, running the demo locally willl allow them to authenticate immediately using GoogleCredentials.

Each user should also make themselves a Storage Admin for the project using the IAM page.


Questions
1) How do I get the covariates for just the 2504 people of interest?
2) Double check logic of generating phenotype
3) How does a research lab configure/agree upon GWAS parameters with another research lab? What is the user flow like for this step?