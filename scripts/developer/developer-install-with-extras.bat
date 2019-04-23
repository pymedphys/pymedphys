conda install -y nbstripout &&^
nbstripout --install &&^
nbstripout --is-installed &&^
conda install -y pymedphys --only-deps &&^
yarn &&^
pip install -e .[docs] &&^
pip install -e .[testing] &&^
pip install -e .[formatting]