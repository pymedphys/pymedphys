poetry run python -m grpc_tools.protoc \
  --python_betterproto_out=../lib/pymedphys/_experimental/_proto/ \
  -I ../. ../proto/*.proto
