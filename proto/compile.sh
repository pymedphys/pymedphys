poetry run python -m grpc_tools.protoc \
  --python_betterproto_out=../lib/pymedphys/_proto/ \
  -I ../. ../proto/*.proto
