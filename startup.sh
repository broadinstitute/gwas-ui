#!/bin/bash
  
sudo apt-get --assume-yes update
sudo apt-get --assume-yes install build-essential
sudo apt-get --assume-yes install clang-3.9
sudo apt-get --assume-yes install libgmp3-dev
sudo apt-get --assume-yes install libssl-dev
sudo apt-get --assume-yes install libomp-dev
sudo apt-get --assume-yes install python3-pip
pip3 install numpy
echo done installing packages

sudo apt-get --assume-yes install git
cd ~
git clone https://github.com/shreyanJ/secure-gwas.git ~/secure-gwas
echo done cloning into repo

curl -O https://www.shoup.net/ntl/ntl-10.3.0.tar.gz
gunzip ntl-10.3.0.tar.gz
tar xf ntl-10.3.0.tar
cp secure-gwas/code/NTL_mod/ZZ.cpp ntl-10.3.0/src/
cp secure-gwas/code/NTL_mod/ZZ.h ntl-10.3.0/include/NTL/
cd ntl-10.3.0/src
./configure NTL_THREAD_BOOST=on
make all
sudo make install
echo done installing NTL library

cd ~/secure-gwas/code
COMP=`which clang++`
sed -i "s|^CPP.*$|CPP = ${COMP}|g" Makefile
sed -i "s|^INCPATHS.*$|INCPATHS = -I/usr/local/include|g" Makefile
sed -i "s|^LDPATH.*$|LDPATH = -L/usr/local/lib|g" Makefile
make
echo done compiling secure gwas code

cd ~/secure-gwas
mkdir gwas_data
echo created folder to store gwas data
