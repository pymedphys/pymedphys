#!/bin/sh

set -ex

cd applications/desktop
yarn
yarn dist
