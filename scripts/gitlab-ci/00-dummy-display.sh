#!/bin/bash

set -ex

apt-get update
apt-get install libgl1-mesa-glx xvfb -y -q

sh -e /etc/init.d/xvfb start