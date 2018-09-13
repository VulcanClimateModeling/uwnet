.PHONY: data docs

#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
# BUCKET = {{ cookiecutter.s3_bucket }}
# PROFILE = {{ cookiecutter.aws_profile }}
PROJECT_NAME = uwnet
PYTHON_INTERPRETER = python

#################################################################################
# COMMANDS                                                                      #
#################################################################################

TRAINING_DATA = data/training_data_lower_atmos.nc
WORKDIR = ~/Data/0

./nextflow:
	wget -qO- https://get.nextflow.io | bash

all: ./nextflow
	./nextflow run main.nf -w $(WORKDIR)  -resume \
		 --numTimePoints=640 --forcingMethod=FD

no_resume:
	./nextflow run main.nf -w $(WORKDIR) --forcingMethod=FD

debug_sam_output: 
	rm -f ~/workspace/models/SAMUWgh/SAM_*
	make all
	@grep 'W range' data/samNN/checks/sam_nn.txt
	@grep 'FQT range' data/samNN/checks/sam_nn.txt
	@grep -v 'FQT range' data/samNN/checks/sam_nn.txt | grep FQT
	@grep FSL data/samNN/checks/sam_nn.txt
	@grep Prec data/samNN/checks/sam_nn.txt

check_sam_output:
	make all
	@grep 'W range' data/samNN/checks/sam_nn.txt
	@grep 'FQT range' data/samNN/checks/sam_nn.txt
	@grep -v 'FQT range' data/samNN/checks/sam_nn.txt | grep FQT
	@grep FSL data/samNN/checks/sam_nn.txt
	@grep Prec data/samNN/checks/sam_nn.txt

print_sam_checks:
	@grep 'W range' data/samNN/checks/sam_nn.txt
	@grep 'FQT range' data/samNN/checks/sam_nn.txt
	@grep -v 'FQT range' data/samNN/checks/sam_nn.txt | grep FQT
	@grep FSL data/samNN/checks/sam_nn.txt
	@grep Prec data/samNN/checks/sam_nn.txt

## Call nextflow to produce the training data.
data:
	snakemake data/training.nc

## train
train:
	./nextflow run train.nf --numEpochs=2 --trainingData $(TRAINING_DATA) -resume


data/subset.nc:
	ncks -O -d y,32 -d z,0,27 -d time,0,100 data/training_data.nc $@

## train on a subset of thed data. This is useful for speeding up the training
train_subset: data/subset.nc
	python -m uwnet.train -n 20 -b 32 -lr .005 -s 5 -l 10 examples/all.yaml data/subset.nc

upload_reports:
	rsync -avz reports/ olympus:~/public_html/reports/uwnet/


docker:
	docker run -it \
		-v /Users:/Users  \
		-v $(shell pwd)/uwnet:/opt/uwnet \
		-w $(shell pwd) nbren12/uwnet bash

build_image:
	docker build -t nbren12/uwnet .

setup:  create_environment install_hooks build_image

create_environment:
	@echo ">>> creating environment from file"
	conda env create -f environment.yml || \
	conda env update -f environment.yml
	@echo ">>> Setting up uwnet in develop mode"
	bash -c "source activate uwnet && python setup.py develop && \
					jupyter labextension install @pyviz/jupyterlab_pyviz"
	@echo ">>> New Environment created...activate by typing"
	@echo "    source activate uwnet"

docs:
	make -C docs html

install_hooks:
	cp -f git-hooks/* .git/hooks/
