# Need to run the following before this script
# docker login registry.gitlab.com

# INFO at https://gitlab.com/help/user/project/container_registry#build-and-push-images

docker build -t registry.gitlab.com/pymedphys/pymedphys/ci .
docker push registry.gitlab.com/pymedphys/pymedphys/ci