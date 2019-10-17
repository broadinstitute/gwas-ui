1. Setup
pip3 install -r requirements.txt

2. Authentication
Each user should download gcloud command line SDK to their machine, and give themselves Compute Admin and Storage Admin roles on IAM

Each user should run `gcloud auth application-default login` in their shell to temporarily set their personal user credentials as the app default credentials for API access. After this step, running the demo locally willl allow them to authenticate immediately using GoogleCredentials.


Questions
1) Double check logic of generating phenotype

Biggest To-Do's Remaining:
1) Add workflow for "Create New GWAS Instance" option.
2) If many parties are running the role of S, just have all IP addresses separated by whitespace in the same line of config.txt, and we can run the protocol one time for each IP address.
3) Some issues with automating VPC network creation:
	- Need a 30 second delay between create network and create subnet.
	- Do we need to worry about firewalls? Both to allow traffic and to prevent traffic on non-GWAS ports?
	- Overlapping subnet ranges if multiple groups running GWAS? Might need database to keep track of IP addresses. Or delete net after done. Also think about adding checks to see if peering or network already exists before adding.
4) Add other parameters to config file (eg num individuals, covariates, etc).
5) Key Generation:
	- For now, just using existing keys with repo.
	- Later, might want to rethink/add protocol for generating new keys and sharing the global key/key pairs. Talk to Hoon.