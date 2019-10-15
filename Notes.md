1. Setup
pip3 install -r requirements.txt

2. Authentication

Each user should run `gcloud auth application-default login` in their shell to temporarily set their personal user credentials as the app default credentials for API access. After this step, running the demo locally willl allow them to authenticate immediately using GoogleCredentials.

Each user should also make themselves a Storage Admin for the project using the IAM page.


Questions
1) Intro to VCF and how it works, how we can convert to text file/compress.
2) In github, only one party has the data. For demo, seems like we're splitting it up. How does the GWAS protocol work in that case?
3) How does a research lab configure/agree upon GWAS parameters with another research lab? What is the user flow like for this step?