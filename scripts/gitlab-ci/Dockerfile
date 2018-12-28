FROM continuumio/miniconda3:latest

RUN conda config --set always_yes yes --set changeps1 no
RUN conda config --add channels conda-forge
RUN conda info -a

RUN conda update -q conda && \
    conda clean -tipsy

RUN conda create -q -n test pytest nbstripout pymedphys && \
    source activate test && \
    conda uninstall pymedphys && \
    conda clean -tipsy

RUN source activate test && \
    pip install --no-cache-dir pytest-pylint pytest-testmon && \
    conda clean -tipsy

RUN MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"` && \
    echo "backend: Agg" > $MATPLOTLIB_RC
