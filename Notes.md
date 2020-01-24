1. Setup
pip3 install -r requirements.txt

2. Authentication
Each user should download gcloud command line SDK to their machine, and give themselves Compute Admin and Storage Admin roles on IAM

Each user should run `gcloud auth application-default login` in their shell to temporarily set their personal user credentials as the app default credentials for API access. After this step, running the demo locally willl allow them to authenticate immediately using GoogleCredentials.

3. Config.txt
-need to agree upon parameters
-need to exchange project names and instance IP addresses (private or external?)

4. Run UI
. ~ /env/bin/activate

Things that need to be updated each round of data sharing/gwas in parameter file:
- Num_inds - each dataset might have data for a different number of individuals
- Cache_file_prefix - one value for each dataset

Assumptions/things that shouldn't change:
- Num_covs shouldn't change cause individuals from 2 separate datasets should have values for the same covariates
- Similarly, Num_snps shouldn't change - basically, the shape of the data (number of columns) should be the same for the two datasets, even if the number of subjects/rows changes

Biggest To-Do's Remaining:
2) If many parties are running the role of S, just have all IP addresses separated by whitespace in the same line of config.txt, and we can run the protocol one time for each IP address.
3) Some issues with VPC networks:
	- Do we need to worry about firewalls? Both to allow traffic and to prevent traffic on non-GWAS ports?
	- Need to avoid overlapping subnet ranges: subnets need to be of the form 10.x.y.0/24, where x and y are distinct for all users. Right, now I just randomly generate x and y - need to change that.
	- Consider deleting a net after GWAS is done, and also think about adding checks to see if peering or network already exists before adding.
	- Need to replace VPC with SSL.
4) Add other parameters to config file (eg ones other than num individuals, covariates, etc).
5) Key Generation:
	- For now, just using existing keys with repo.
	- Later, might want to rethink/add protocol for generating new keys and sharing the global key/key pairs. Talk to Hoon.
6) GWAS Orchestration
	- Issue 1: when transitioning from Data Sharing stage to GWAS stage, suddenly connection can't be created. Issue is probably that there's already a spawned process that isn't being killed? When you fix this, should probably eliminate the whole navigate to new page with button thingy.
	- Isuse 2: if user 1 presses start and user 2 presses start 10 minutes later, won't work
	- Need to think about how to orchestrate the GWAS process using some central service
7) pos.txt - need to take union
8) after specifying parameters, populate a table to show the user -> data parameters should be generated based on datasets themselves
9) Concatenating datasets/running Data Client many times in a row before running GWAS once; also have delay between successive commands otherwise networking gets ruined, maybe 60 seconds?
	- instead of concatenating datasets, can run Data Sharing Client many times in a row and GWAS once, but write the secret shares corresponding to each data shard to separate files. Then, during GWAS, read in the covariate/phenotype/genotype data from multiple files instead of a single file by looping over it. For the data sharing part of it, need to update par.txt file with a unique Cache_File_Prefix and also the number of individuals/number of covariates
10) doing all data unzipping etc in bucket and keeping in bucket to avoid storage issues on compute instance -> maybe a better way to do this is to create an endpoint for uploading data to google cloud storage in which user uploads a VCF file, configures parameters, and gives bucket name and filename - the local webservice then runs the preprocessing and then uploads the file to a new google cloud storage bucket


Network/Instance Workflow - what I like about this is that it ties instances to networks in a 1:1 mapping.
1. Create a network - call it "net-p0" for example.
2. Add a subnet to the network for a given region - call it "sub-p0" for example. Make sure to use non-overlapping IP ranges, eg 10.i.0.0/24 for the network corresponding to instance with ID i.
3. Add firewall rules allowing ingress on the network - call it "net-p0-allow-ingress". Can finetune logic on choosing which instances, ports, and communication modes it applies to later. Give it priority 1000.
4. Add peering between networks of each pair of projects/CPs - call it "peer-p0-p1" for example. Will this have to be moved to later? Not sure. Need to know that others have created instance, so probably yeah.
5. Create a new GWAS instance and attach it to the network.
6. Continue with workflow as before: choose instance, load data, update parameters, and run GWAS.