set -ex

if [[ "$OSTYPE" != "linux-gnu" ]]; then
  source activate pymedphys
else
  source /home/vsts/.conda/envs/pymedphys/bin/activate pymedphys
fi