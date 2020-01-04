C:
cd C:\Users\sbiggs\git\scriptedforms\deploy\jupyterhub-docker

bash -c "export DOCKER_HOST=tcp://localhost:2375; make notebook_image"
bash -c "export DOCKER_HOST=tcp://localhost:2375; /home/sbiggs/miniconda3/bin/docker-compose up"
bash -c "export DOCKER_HOST=tcp://localhost:2375; /home/sbiggs/miniconda3/bin/docker-compose stop"
