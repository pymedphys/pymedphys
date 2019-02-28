# Based off of https://hub.docker.com/r/continuumio/miniconda3/dockerfile

FROM osimis/orthanc:19.1.1

ENV PATH /opt/conda/bin:$PATH

RUN apt-get update --fix-missing && \
  apt-get install -y wget bzip2 ca-certificates curl git && \
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
RUN conda install pymedphys