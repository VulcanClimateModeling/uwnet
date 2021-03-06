FROM nvidia/cuda:10.0-cudnn7-devel-ubuntu18.04

RUN apt-get update && apt-get install -y \
    libnetcdff-dev libnetcdf-dev \
    build-essential gfortran \
    libmpich-dev  csh  nco \
    gdb curl git cmake

# compile sam utilities
ADD ext/sam/UTIL /sam/UTIL
RUN make -C /sam/UTIL

# Install miniconda to /miniconda
RUN curl -LO http://repo.continuum.io/miniconda/Miniconda3-4.6.14-Linux-x86_64.sh
RUN bash Miniconda3-4.6.14-Linux-x86_64.sh -p /miniconda -b
RUN rm Miniconda3-4.6.14-Linux-x86_64.sh
ENV PATH=/miniconda/bin:${PATH}

# install pfunit
# RUN git clone git://git.code.sf.net/p/pfunit/code /tmp/pFUnit
# ADD http://superb-sea2.dl.sourceforge.net/project/pfunit/Source/pFUnit-3.2.9.tgz /tmp/
ADD ext/pFUnit-3.2.9.tgz /tmp/
ENV F90=gfortran
ENV F90_VENDOR=GNU
ENV PFUNIT=/opt/pfunit/pfunit-serial
RUN cd /tmp/pFUnit-3.2.9 && \
    make &&\
    make install INSTALL_DIR=${PFUNIT}

# add conda packages
RUN conda update -y conda 
ADD environment.yml /tmp/environment.yml
RUN conda env update -f /tmp/environment.yml
ENV PATH=/miniconda/envs/uwnet/bin:$PATH
RUN conda install -n uwnet netcdf4


# add callpy library
ADD ext/sam/ext/call_py_fort /opt/call_py_fort
ENV PYTHONPATH=/opt/call_py_fort/src/:/opt/call_py_fort/test:$PYTHONPATH
ENV CALLPY=/opt/call_py_fort
RUN cd /opt/call_py_fort/ && make install
ENV LD_LIBRARY_PATH=/usr/local/lib

# Install SAM Python modules
ENV PYTHONPATH=/opt/sam/SRC/python:${PYTHONPATH}
ENV PYTHONPATH=/opt/sam/SCRIPTS/python/:/opt/:${PYTHONPATH}

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Install SAM
ADD ext/sam /opt/sam
ADD setup/docker /opt/sam_compile_scripts
ENV LOCAL_FLAGS=/opt/sam_compile_scripts/local_flags.mk
RUN bash -c "cd /opt/sam && export NX=128 && export NY=64 && export NZ=34 && export NSUBX=1 && export NSUBY=1 && ./Build"
RUN bash -c "cd /opt/sam && export NX=512 && export NY=256 && export NZ=34 && export NSUBX=2 && export NSUBY=2 && ./Build"

# install uwnet
ADD . /opt/uwnet
ENV PYTHONPATH=/opt/uwnet:$PYTHONPATH
