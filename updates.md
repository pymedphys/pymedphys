## Dependency Updates

```diff
<     "python_full_version >= '3.12'",
>     "python_full_version >= '3.12' and sys_platform == 'win32'",
>     "python_full_version >= '3.12' and sys_platform == 'emscripten'",
>     "python_full_version >= '3.12' and sys_platform != 'emscripten' and sys_platform != 'win32'",
< version = "0.67.0"
> version = "0.84.0"
>     { name = "docstring-parser" },
< sdist = { url = "https://files.pythonhosted.org/packages/09/08/ee91464cd821e6fca52d9a23be44815c95edd3c1cf1e844b2c5e85f0d57f/anthropic-0.67.0.tar.gz", hash = "sha256:d1531b210ea300c73423141d29bcee20fcd24ef9f426f6437c0a5d93fc98fb8e", size = 441639, upload-time = "2025-09-10T14:47:18.137Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/04/ea/0869d6df9ef83dcf393aeefc12dd81677d091c6ffc86f783e51cf44062f2/anthropic-0.84.0.tar.gz", hash = "sha256:72f5f90e5aebe62dca316cb013629cfa24996b0f5a4593b8c3d712bc03c43c37", size = 539457, upload-time = "2026-02-25T05:22:38.54Z" }
<     { url = "https://files.pythonhosted.org/packages/5c/9d/9adbda372710918cc8271d089a2ceae4d977a125f90bc3c4b456bca4f281/anthropic-0.67.0-py3-none-any.whl", hash = "sha256:f80a81ec1132c514215f33d25edeeab1c4691ad5361b391ebb70d528b0605b55", size = 317126, upload-time = "2025-09-10T14:47:16.351Z" },
>     { url = "https://files.pythonhosted.org/packages/64/ca/218fa25002a332c0aa149ba18ffc0543175998b1f65de63f6d106689a345/anthropic-0.84.0-py3-none-any.whl", hash = "sha256:861c4c50f91ca45f942e091d83b60530ad6d4f98733bfe648065364da05d29e7", size = 455156, upload-time = "2026-02-25T05:22:40.468Z" },
< version = "4.10.0"
> version = "4.12.1"
<     { name = "sniffio" },
< sdist = { url = "https://files.pythonhosted.org/packages/f1/b4/636b3b65173d3ce9a38ef5f0522789614e590dab6a8d505340a4efe4c567/anyio-4.10.0.tar.gz", hash = "sha256:3f3fae35c96039744587aa5b8371e7e8e603c0702999535961dd336026973ba6", size = 213252, upload-time = "2025-08-04T08:54:26.451Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/96/f0/5eb65b2bb0d09ac6776f2eb54adee6abe8228ea05b20a5ad0e4945de8aac/anyio-4.12.1.tar.gz", hash = "sha256:41cfcc3a4c85d3f05c932da7c26d0201ac36f72abd4435ba90d0464a3ffed703", size = 228685, upload-time = "2026-01-06T11:45:21.246Z" }
<     { url = "https://files.pythonhosted.org/packages/6f/12/e5e0282d673bb9746bacfb6e2dba8719989d3660cdb2ea79aee9a9651afb/anyio-4.10.0-py3-none-any.whl", hash = "sha256:60e474ac86736bbfd6f210f7a61218939c318f43f9972497381f1c5e930ed3d1", size = 107213, upload-time = "2025-08-04T08:54:24.882Z" },
>     { url = "https://files.pythonhosted.org/packages/38/0e/27be9fdef66e72d64c0cdc3cc2823101b80585f8119b5c112c2e8f5f7dab/anyio-4.12.1-py3-none-any.whl", hash = "sha256:d405828884fc140aa80a3c667b8beed277f1dfedec42ba031bd6ac3db606ab6c", size = 113592, upload-time = "2026-01-06T11:45:19.497Z" },
< version = "3.3.11"
> version = "4.0.4"
< sdist = { url = "https://files.pythonhosted.org/packages/18/74/dfb75f9ccd592bbedb175d4a32fc643cf569d7c218508bfbd6ea7ef9c091/astroid-3.3.11.tar.gz", hash = "sha256:1e5a5011af2920c7c67a53f65d536d65bfa7116feeaf2354d8b94f29573bb0ce", size = 400439, upload-time = "2025-07-13T18:04:23.177Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/07/63/0adf26577da5eff6eb7a177876c1cfa213856be9926a000f65c4add9692b/astroid-4.0.4.tar.gz", hash = "sha256:986fed8bcf79fb82c78b18a53352a0b287a73817d6dbcfba3162da36667c49a0", size = 406358, upload-time = "2026-02-07T23:35:07.509Z" }
<     { url = "https://files.pythonhosted.org/packages/af/0f/3b8fdc946b4d9cc8cc1e8af42c4e409468c84441b933d037e101b3d72d86/astroid-3.3.11-py3-none-any.whl", hash = "sha256:54c760ae8322ece1abd213057c4b5bba7c49818853fc901ef09719a60dbf9dec", size = 275612, upload-time = "2025-07-13T18:04:21.07Z" },
>     { url = "https://files.pythonhosted.org/packages/b0/cf/1c5f42b110e57bc5502eb80dbc3b03d256926062519224835ef08134f1f9/astroid-4.0.4-py3-none-any.whl", hash = "sha256:52f39653876c7dec3e3afd4c2696920e05c83832b9737afc21928f2d2eb7a753", size = 276445, upload-time = "2026-02-07T23:35:05.344Z" },
< version = "3.0.0"
> version = "3.0.1"
< sdist = { url = "https://files.pythonhosted.org/packages/4a/e7/82da0a03e7ba5141f05cce0d302e6eed121ae055e0456ca228bf693984bc/asttokens-3.0.0.tar.gz", hash = "sha256:0dcd8baa8d62b0c1d118b399b2ddba3c4aff271d0d7a9e0d4c1681c79035bbc7", size = 61978, upload-time = "2024-11-30T04:30:14.439Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/be/a5/8e3f9b6771b0b408517c82d97aed8f2036509bc247d46114925e32fe33f0/asttokens-3.0.1.tar.gz", hash = "sha256:71a4ee5de0bde6a31d64f6b13f2293ac190344478f081c3d1bccfcf5eacb0cb7", size = 62308, upload-time = "2025-11-15T16:43:48.578Z" }
<     { url = "https://files.pythonhosted.org/packages/25/8a/c46dcc25341b5bce5472c718902eb3d38600a903b14fa6aeecef3f21a46f/asttokens-3.0.0-py3-none-any.whl", hash = "sha256:e3078351a059199dd5138cb1c706e6430c05eff2ff136af5eb4790f9d28932e2", size = 26918, upload-time = "2024-11-30T04:30:10.946Z" },
>     { url = "https://files.pythonhosted.org/packages/d2/39/e7eaf1799466a4aef85b6a4fe7bd175ad2b1c6345066aa33f1f58d4b18d0/asttokens-3.0.1-py3-none-any.whl", hash = "sha256:15a3ebc0f43c2d0a50eeafea25e19046c68398e487b9f1f5b517f7c0f40f976a", size = 27047, upload-time = "2025-11-15T16:43:16.109Z" },
< version = "25.3.0"
> version = "25.4.0"
< sdist = { url = "https://files.pythonhosted.org/packages/5a/b0/1367933a8532ee6ff8d63537de4f1177af4bff9f3e829baf7331f595bb24/attrs-25.3.0.tar.gz", hash = "sha256:75d7cefc7fb576747b2c81b4442d4d4a1ce0900973527c011d1030fd3bf4af1b", size = 812032, upload-time = "2025-03-13T11:10:22.779Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/6b/5c/685e6633917e101e5dcb62b9dd76946cbb57c26e133bae9e0cd36033c0a9/attrs-25.4.0.tar.gz", hash = "sha256:16d5969b87f0859ef33a48b35d55ac1be6e42ae49d5e853b597db70c35c57e11", size = 934251, upload-time = "2025-10-06T13:54:44.725Z" }
<     { url = "https://files.pythonhosted.org/packages/77/06/bb80f5f86020c4551da315d78b3ab75e8228f89f0162f2c3a819e407941a/attrs-25.3.0-py3-none-any.whl", hash = "sha256:427318ce031701fea540783410126f03899a97ffc6f61596ad581ac2e40e3bc3", size = 63815, upload-time = "2025-03-13T11:10:21.14Z" },
>     { url = "https://files.pythonhosted.org/packages/3a/2a/7cc015f5b9f5db42b7d48157e23356022889fc354a2813c15934b7cb5c0e/attrs-25.4.0-py3-none-any.whl", hash = "sha256:adcf7e2a1fb3b36ac48d97835bb6d8ade15b8dcce26aba8bf1d14847b57a3373", size = 67615, upload-time = "2025-10-06T13:54:43.17Z" },
< version = "2.17.0"
> version = "2.18.0"
< sdist = { url = "https://files.pythonhosted.org/packages/7d/6b/d52e42361e1aa00709585ecc30b3f9684b3ab62530771402248b1b1d6240/babel-2.17.0.tar.gz", hash = "sha256:0c54cffb19f690cdcc52a3b50bcbf71e07a808d1c80d549f2459b9d2cf0afb9d", size = 9951852, upload-time = "2025-02-01T15:17:41.026Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/7d/b2/51899539b6ceeeb420d40ed3cd4b7a40519404f9baf3d4ac99dc413a834b/babel-2.18.0.tar.gz", hash = "sha256:b80b99a14bd085fcacfa15c9165f651fbb3406e66cc603abf11c5750937c992d", size = 9959554, upload-time = "2026-02-01T12:30:56.078Z" }
<     { url = "https://files.pythonhosted.org/packages/b7/b8/3fe70c75fe32afc4bb507f75563d39bc5642255d1d94f1f23604725780bf/babel-2.17.0-py3-none-any.whl", hash = "sha256:4d0b53093fdfb4b21c92b5213dba5a1b23885afa8383709427046b21c366e5f2", size = 10182537, upload-time = "2025-02-01T15:17:37.39Z" },
>     { url = "https://files.pythonhosted.org/packages/77/f5/21d2de20e8b8b0408f0681956ca2c69f1320a3848ac50e6e7f39c6159675/babel-2.18.0-py3-none-any.whl", hash = "sha256:e2b422b277c2b9a9630c1d7903c2a00d0830c409c59ac8cae9081c92f1aeba35", size = 10196845, upload-time = "2026-02-01T12:30:53.445Z" },
< version = "4.13.5"
> version = "4.14.3"
< sdist = { url = "https://files.pythonhosted.org/packages/85/2e/3e5079847e653b1f6dc647aa24549d68c6addb4c595cc0d902d1b19308ad/beautifulsoup4-4.13.5.tar.gz", hash = "sha256:5e70131382930e7c3de33450a2f54a63d5e4b19386eab43a5b34d594268f3695", size = 622954, upload-time = "2025-08-24T14:06:13.168Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/c3/b0/1c6a16426d389813b48d95e26898aff79abbde42ad353958ad95cc8c9b21/beautifulsoup4-4.14.3.tar.gz", hash = "sha256:6292b1c5186d356bba669ef9f7f051757099565ad9ada5dd630bd9de5fa7fb86", size = 627737, upload-time = "2025-11-30T15:08:26.084Z" }
<     { url = "https://files.pythonhosted.org/packages/04/eb/f4151e0c7377a6e08a38108609ba5cede57986802757848688aeedd1b9e8/beautifulsoup4-4.13.5-py3-none-any.whl", hash = "sha256:642085eaa22233aceadff9c69651bc51e8bf3f874fb6d7104ece2beb24b47c4a", size = 105113, upload-time = "2025-08-24T14:06:14.884Z" },
>     { url = "https://files.pythonhosted.org/packages/1a/39/47f9197bdd44df24d67ac8893641e16f386c984a0619ef2ee4c51fbbc019/beautifulsoup4-4.14.3-py3-none-any.whl", hash = "sha256:0918bfe44902e6ad8d57732ba310582e98da931428d231a5ecb9e7c703a735bb", size = 107721, upload-time = "2025-11-30T15:08:24.087Z" },
< version = "2025.8.3"
> version = "2026.2.25"
```
