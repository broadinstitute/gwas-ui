# gwas-ui
This codebase provides a simple interface for running secure GWAS in the public cloud.

**Setup Instructions**
1. Download the codebase and run `pip3 install -r requirements.txt` to install all dependencies.
2. Register for a Google Cloud account and create a new Project. Also give yourself Compute Admin and Storage Admin roles on IAM.
3. Download the Google Cloud command line SDK to your machine.
4. Run `gcloud auth application-default login` on your machine to temporarily your personal user credentials as the app default credentials for API access. After this step, the backend will be able to immediately authenticate all cloud operations using GoogleCredentials.
5. Generate a shared (across all collaborating parties) config.txt file using the provided template. 
6. Finally, run `python3 main.py` to launch the interface, and navigate to localhost:8080 in your browser to begin setting up and running your GWAS study.

**Future Improvements**
1. *Key Generation.* Add a streamlined method for generating the AES communication keys and sharing them between parties.
2. *Synchronization.* Add a mechanism for collaborating parties to synchronize when they begin running the GWAS protocol. Along a similar vein, also add a way to check that the final config files used by collaborating parties match up.
3. *Data Preprocessing.* Update the code for preprocessing the GWAS input datasets to handle a larger number of use cases. For instance, the code currently assumes that all input datasets use the same exact list of genomic positions. Additionally, the code for converting the VCF file for genomic data is relatively slow, so perform preprocessing steps in Google Cloud rather than locally.
