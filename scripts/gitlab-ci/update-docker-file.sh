# Need to run the following before this script
# docker login registry.gitlab.com

# INFO at https://gitlab.com/help/user/project/container_registry#build-and-push-images

DIR=`dirname "$0"`

docker build -t registry.gitlab.com/pymedphys/pymedphys/ci $DIR
docker push registry.gitlab.com/pymedphys/pymedphys/ci