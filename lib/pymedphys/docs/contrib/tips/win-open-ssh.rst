Git with SSH on Windows
=======================

SSH is optional. The setup guide uses an HTTPS clone URL; use Git Credential
Manager or GitHub CLI if you prefer HTTPS authentication.

To use SSH, follow GitHub's maintained instructions for:

* `Generating an SSH key and adding it to the agent
  <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent>`_
* `Adding the public key to your GitHub account
  <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account>`_
* `Testing the connection
  <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection>`_

Select the Windows instructions. Git for Windows and Windows OpenSSH can use
different SSH executables and agents; ensure Git uses the agent holding your
key. GitHub's guide explains the Windows configuration.

Then clone with ``git clone git@github.com:pymedphys/pymedphys.git``, or use
your fork's SSH URL.
