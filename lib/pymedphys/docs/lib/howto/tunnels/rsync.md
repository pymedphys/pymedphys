# Backups using rsync

## Background

We want all data to have a "single source of truth". As such, important data
has its reference location at only one site. All day-to-day usage of that data
is undergone via network traffic to that reference location. The downside of
this is that a network interruption, such as the remote data storage location
having a power outage, makes this data unavailable.

As such, just-in-case, important remote datastores are synced locally. This
document details an example of one such local sync.

## Pre-requisites

* SSH Tunnels forwarding through the SAMBA port of the remote file share
  * For the purpose of this document it will be assumed that this share is
    accessible at `rccc-ssh/Physics` at port `44448`. The directory to be
    backed up is `Physics`
* A local SAMBA share for storing the backup
  * For the purpose of this document it will be assumed that this share is
    accessible at `rccc-ssh/D`. The directory to back up to is
    `PhysicsDriveBackup`
* A username and password that is able to access both SAMBA shares
  * For the purpose here, this username will be `pexit` and the remote share
    will be on the domain `nbccc`, and the local share will be on the domain
    `rccc`.
* An Ubuntu 20.04 instance with access to both the forwarded SAMBA share and
  the local SAMBA share
  * For the purpose here, this instance is a VM within Hyper-V with user login
    name `pexit`.

## Overview

The general approach here will be to:

* Create the permanent SAMBA mount points via fstab
* Set up rsync to run via cron

## Permanently mount the SAMBA shares

To begin, we need to create two mount points. On our machine this was done by
running:

```bash
sudo mkdir -p /media/rccc-ssh/D /media/tunnel-nbcc-pdc/Physics
```

Then, to create the permanent mounts both `fstab` and `cifs-utils` were
utilised. This was adapted from the instructions over at
<https://wiki.ubuntu.com/MountWindowsSharesPermanently>.

Firstly `cifs-utils` was installed:

```bash
sudo apt install cifs-utils
```

Next, a file at `~/.smbcredentials` was created with the contents:

```text
username=pexit
password=YOUR_PASSWORD_GOES_HERE
```

Then the read/write permissions of this file were set as such:

```bash
chmod 600 .smbcredentials
```

Next, the contents of `/etc/fstab` was updated to include the following:

```fstab
//rccc-ssh/Physics  /media/tunnel-nbcc-pdc/Physics  cifs  user,uid=pexit,credentials=/home/pexit/.smbcredentials,domain=nbccc,iocharset=utf8,port=44448  0  0
//rccc-ssh/D        /media/rccc-ssh/D               cifs  user,uid=pexit,credentials=/home/pexit/.smbcredentials,domain=rccc,iocharset=utf8              0  0
```

These new mount points can be tested by running
`mount /media/tunnel-nbcc-pdc/Physics` and `mount /media/rccc-ssh/D`

## Setup rsync crontab

These instructions for setting up `rsync` are adapted from
<https://www.howtogeek.com/135533/how-to-use-rsync-to-backup-your-data-on-linux/>

To set up the `crontab` run `crontab -e`, then append the following to the
bottom of that file:

```crontab
0 1 * * * mount /media/rccc-ssh/D ; mount /media/tunnel-nbcc-pdc/Physics ; timeout 4h rsync -av --delete /media/tunnel-nbcc-pdc/Physics/Physics/ /media/rccc-ssh/D/PhysicsDriveBackup/
```

This will set up cron to make sure the appropriate directories are mounted and
then runs `rsync` each night at 1 am. If the task hasn't completed by 5 am it
is stopped ready for it to continue the task on the following night.
