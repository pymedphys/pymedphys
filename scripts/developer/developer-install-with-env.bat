conda deactivate
conda info --envs | grep "pmp"
if %ERRORLEVEL% EQU 0 (conda env remove -y --name pmp)
conda create -y --name pmp python=3.7 &&^
conda activate pmp &&^
conda install -y nbstripout &&^
nbstripout --install &&^
nbstripout --is-installed &&^
conda install -y pymedphys --only-deps &&^
yarn