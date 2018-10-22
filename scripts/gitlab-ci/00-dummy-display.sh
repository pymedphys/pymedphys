#!/bin/bash

set -ex

apt-get update
apt-get install libgl1-mesa-glx xvfb -qq

Xvfb :99 &