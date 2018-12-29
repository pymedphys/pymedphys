FROM continuumio/miniconda3:latest

RUN conda config --set always_yes yes --set changeps1 no

RUN conda config --add channels conda-forge
RUN conda info -a

RUN conda update -q conda && \
    conda clean -tisy

ADD environment.yml environment.yml

RUN conda env create -f environment.yml && \
    conda clean -tisy && \
    sed -i '$ d' ~/.bashrc && \
    echo "conda activate pymedphys" >> ~/.bashrc

RUN bash -c "conda install -q pytest nbstripout pylint coverage && \
    conda clean -tisy"

RUN bash -c "pip install --no-cache-dir pytest-pylint pytest-testmon && \
    conda clean -tisy"

RUN bash -c 'MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"` && \
    echo "backend: Agg" > $MATPLOTLIB_RC'
