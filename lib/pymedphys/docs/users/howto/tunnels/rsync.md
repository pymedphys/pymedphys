# Backups using rsync

```{note}
This is a site-specific example originally used with Ubuntu 20.04. Use a
supported OS for a new deployment and adjust the shares, accounts, and paths.
The mirror below propagates source deletions; it does not provide versioned
backup history.
```

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
* An Ubuntu instance with access to both the forwarded SAMBA share and
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
utilised. See Ubuntu's current guide to
[mounting CIFS shares permanently](https://ubuntu.com/server/docs/how-to/samba/mount-cifs-shares-permanently/).

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
chmod 600 ~/.smbcredentials
```

Next, the contents of `/etc/fstab` was updated to include the following:

```text
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

```text
0 1 * * * (mountpoint -q /media/rccc-ssh/D || mount /media/rccc-ssh/D) && (mountpoint -q /media/tunnel-nbcc-pdc/Physics || mount /media/tunnel-nbcc-pdc/Physics) && mountpoint -q /media/rccc-ssh/D && mountpoint -q /media/tunnel-nbcc-pdc/Physics && test -d /media/tunnel-nbcc-pdc/Physics/Physics && timeout 4h rsync -av --delete /media/tunnel-nbcc-pdc/Physics/Physics/ /media/rccc-ssh/D/PhysicsDriveBackup/
```

This runs at 1 am and proceeds only after both mount points and the source
directory are present. The previous semicolon-separated command continued
even when mounting failed. Run an initial `rsync` with `--dry-run` and inspect
the source and destination before enabling `--delete`.

The four-hour timeout applies to `rsync` after the mount checks finish. It
does not put a deadline on a blocked mount operation, and the next night's
run rechecks the files rather than resuming a saved job. Monitor the command's
exit status and keep separate versioned backups when recovery from accidental
deletion is required.
