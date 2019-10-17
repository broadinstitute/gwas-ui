1. Setup
pip3 install -r requirements.txt

2. Authentication
Each user should download gcloud command line SDK to their machine, and give themselves Compute Admin and Storage Admin roles on IAM

Each user should run `gcloud auth application-default login` in their shell to temporarily set their personal user credentials as the app default credentials for API access. After this step, running the demo locally willl allow them to authenticate immediately using GoogleCredentials.

3. Config.txt
-need to agree upon parameters
-need to exchange project names and instance IP addresses (private or external?)


Questions
1) Double check logic of generating phenotype

Biggest To-Do's Remaining:
1) Add workflow for "Create New GWAS Instance" option.
	- Note that this will involve changing the workflow of the demo significantly, because the network needs to be configured before you create the instance. So each project needs to first create a new network, then create the instance, then do all the other config stuff. New issue this brings up: when creating a machine that is both S and CP2, do you create 2 networks? And attach it to both? Or create just one network. Latter makes more sense because a machine can always communicate with itself.
2) If many parties are running the role of S, just have all IP addresses separated by whitespace in the same line of config.txt, and we can run the protocol one time for each IP address.
3) Some issues with automating VPC network creation (basically this is barely done):
	- When creating a subnet, need to make sure the IP address of your instance is actually covered by that subnet LOL.
	- Need a 30 second delay between create network and create subnet. Also seems like we need a delay between successive attempts to add a new peering to the same machine sometimes.
	- Update code on network creation to use Global routing
	- Do we need to worry about firewalls? Both to allow traffic and to prevent traffic on non-GWAS ports?
	- Need to avoid overlapping subnet ranges: make sure all participants ensure the first 3 digits of their instance IP are different, which amounts to creating them in different regions. Then for each subnet, take x.y.z.0/24 for the subnet, where x.y.z.w is the IP address of the instance from that project. Consider deleting a net after GWAS is done, and also think about adding checks to see if peering or network already exists before adding.
4) Add other parameters to config file (eg num individuals, covariates, etc).
5) Key Generation:
	- For now, just using existing keys with repo.
	- Later, might want to rethink/add protocol for generating new keys and sharing the global key/key pairs. Talk to Hoon.


Network/Instance Workflow - what I like about this is that it ties instances to networks in a 1:1 mapping.
1. Create a network - call it "net-p0" for example.
2. Add a subnet to the network for a given region - call it "sub-p0" for example. Make sure to use non-overlapping IP ranges, eg 10.i.0.0/24 for the network corresponding to instance with ID i.
3. Add firewall rules allowing ingress on the network - call it "net-p0-allow-ingress". Can finetune logic on choosing which instances, ports, and communication modes it applies to later. Give it priority 1000.
4. Add peering between networks of each pair of projects/CPs - call it "peer-p0-p1" for example. Will this have to be moved to later? Not sure. Need to know that others have created instance, so probably yeah.
5. Create a new GWAS instance and attach it to the network.
6. Continue with workflow as before: choose instance, load data, update parameters, and run GWAS.