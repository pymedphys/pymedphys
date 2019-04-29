# Based off of https://hub.docker.com/r/continuumio/miniconda3/dockerfile

FROM osimis/orthanc:19.1.1

ENV PATH /opt/conda/bin:$PATH

RUN apt-get update --fix-missing && \
  apt-get install -y wget bzip2 ca-certificates curl git apt-transport-https python-software-properties && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-4.5.11-Linux-x86_64.sh -O ~/miniconda.sh && \
  /bin/bash ~/miniconda.sh -b -p /opt/conda && \
  rm ~/miniconda.sh && \
  /opt/conda/bin/conda clean -tipsy && \
  ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
  echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
  echo "conda activate base" >> ~/.bashrc

RUN conda update -n base -c defaults conda
RUN conda config --add channels conda-forge
RUN conda install pymedphys && \
  conda clean -tipsy

RUN curl -sS https://deb.nodesource.com/gpgkey/nodesource.gpg.key | apt-key add -
RUN echo 'deb https://deb.nodesource.com/node_10.x xenial main' | tee /etc/apt/sources.list.d/nodesource.list

RUN curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -
RUN echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list

RUN apt-get update --fix-missing && \
  apt-get install -y --no-install-recommends yarn nodejs && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*
