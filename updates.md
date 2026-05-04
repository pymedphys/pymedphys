## Dependency Updates

```diff
<     "python_full_version >= '3.12'",
<     "python_full_version == '3.11.*'",
>     "python_full_version >= '3.12' and sys_platform == 'win32'",
>     "python_full_version == '3.11.*' and sys_platform == 'win32'",
>     "python_full_version >= '3.12' and sys_platform == 'emscripten'",
>     "python_full_version == '3.11.*' and sys_platform == 'emscripten'",
>     "python_full_version >= '3.12' and sys_platform != 'emscripten' and sys_platform != 'win32'",
>     "python_full_version == '3.11.*' and sys_platform != 'emscripten' and sys_platform != 'win32'",
< version = "0.74.1"
> version = "0.97.0"
< sdist = { url = "https://files.pythonhosted.org/packages/d7/7b/609eea5c54ae69b1a4a94169d4b0c86dc5c41b43509989913f6cdc61b81d/anthropic-0.74.1.tar.gz", hash = "sha256:04c087b2751385c524f6d332d066a913870e4de8b3e335fb0a0c595f1f88dc6e", size = 428981, upload-time = "2025-11-19T22:17:31.533Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/14/93/f66ea8bfe39f2e6bb9da8e27fa5457ad2520e8f7612dfc547b17fad55c4d/anthropic-0.97.0.tar.gz", hash = "sha256:021e79fd8e21e90ad94dc5ba2bbbd8b1599f424f5b1fab6c06204009cab764be", size = 669502, upload-time = "2026-04-23T20:52:34.445Z" }
<     { url = "https://files.pythonhosted.org/packages/dd/45/6b18d0692302b8cbc01a10c35b43953d3c4172fbd4f83337b8ed21a8eaa4/anthropic-0.74.1-py3-none-any.whl", hash = "sha256:b07b998d1cee7f41d9f02530597d7411672b362cc2417760a40c0167b81c6e65", size = 371473, upload-time = "2025-11-19T22:17:29.998Z" },
>     { url = "https://files.pythonhosted.org/packages/53/b6/8e851369fa661ad0fef2ae6266bf3b7d52b78ccf011720058f4adaca59e2/anthropic-0.97.0-py3-none-any.whl", hash = "sha256:8a1a472dfabcfc0c52ff6a3eecf724ac7e07107a2f6e2367be55ceb42f5d5613", size = 662126, upload-time = "2026-04-23T20:52:32.377Z" },
< version = "4.11.0"
> version = "4.13.0"
<     { name = "sniffio" },
< sdist = { url = "https://files.pythonhosted.org/packages/c6/78/7d432127c41b50bccba979505f272c16cbcadcc33645d5fa3a738110ae75/anyio-4.11.0.tar.gz", hash = "sha256:82a8d0b81e318cc5ce71a5f1f8b5c4e63619620b63141ef8c995fa0db95a57c4", size = 219094, upload-time = "2025-09-23T09:19:12.58Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/19/14/2c5dd9f512b66549ae92767a9c7b330ae88e1932ca57876909410251fe13/anyio-4.13.0.tar.gz", hash = "sha256:334b70e641fd2221c1505b3890c69882fe4a2df910cba14d97019b90b24439dc", size = 231622, upload-time = "2026-03-24T12:59:09.671Z" }
<     { url = "https://files.pythonhosted.org/packages/15/b3/9b1a8074496371342ec1e796a96f99c82c945a339cd81a8e73de28b4cf9e/anyio-4.11.0-py3-none-any.whl", hash = "sha256:0287e96f4d26d4149305414d4e3bc32f0dcd0862365a4bddea19d7a1ec38c4fc", size = 109097, upload-time = "2025-09-23T09:19:10.601Z" },
>     { url = "https://files.pythonhosted.org/packages/da/42/e921fccf5015463e32a3cf6ee7f980a6ed0f395ceeaa45060b61d86486c2/anyio-4.13.0-py3-none-any.whl", hash = "sha256:08b310f9e24a9594186fd75b4f73f4a4152069e3853f1ed8bfbf58369f4ad708", size = 114353, upload-time = "2026-03-24T12:59:08.246Z" },
< version = "4.0.2"
> version = "4.0.4"
< sdist = { url = "https://files.pythonhosted.org/packages/b7/22/97df040e15d964e592d3a180598ace67e91b7c559d8298bdb3c949dc6e42/astroid-4.0.2.tar.gz", hash = "sha256:ac8fb7ca1c08eb9afec91ccc23edbd8ac73bb22cbdd7da1d488d9fb8d6579070", size = 405714, upload-time = "2025-11-09T21:21:18.373Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/07/63/0adf26577da5eff6eb7a177876c1cfa213856be9926a000f65c4add9692b/astroid-4.0.4.tar.gz", hash = "sha256:986fed8bcf79fb82c78b18a53352a0b287a73817d6dbcfba3162da36667c49a0", size = 406358, upload-time = "2026-02-07T23:35:07.509Z" }
<     { url = "https://files.pythonhosted.org/packages/93/ac/a85b4bfb4cf53221513e27f33cc37ad158fce02ac291d18bee6b49ab477d/astroid-4.0.2-py3-none-any.whl", hash = "sha256:d7546c00a12efc32650b19a2bb66a153883185d3179ab0d4868086f807338b9b", size = 276354, upload-time = "2025-11-09T21:21:16.54Z" },
>     { url = "https://files.pythonhosted.org/packages/b0/cf/1c5f42b110e57bc5502eb80dbc3b03d256926062519224835ef08134f1f9/astroid-4.0.4-py3-none-any.whl", hash = "sha256:52f39653876c7dec3e3afd4c2696920e05c83832b9737afc21928f2d2eb7a753", size = 276445, upload-time = "2026-02-07T23:35:05.344Z" },
< version = "25.4.0"
> version = "26.1.0"
< sdist = { url = "https://files.pythonhosted.org/packages/6b/5c/685e6633917e101e5dcb62b9dd76946cbb57c26e133bae9e0cd36033c0a9/attrs-25.4.0.tar.gz", hash = "sha256:16d5969b87f0859ef33a48b35d55ac1be6e42ae49d5e853b597db70c35c57e11", size = 934251, upload-time = "2025-10-06T13:54:44.725Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/9a/8e/82a0fe20a541c03148528be8cac2408564a6c9a0cc7e9171802bc1d26985/attrs-26.1.0.tar.gz", hash = "sha256:d03ceb89cb322a8fd706d4fb91940737b6642aa36998fe130a9bc96c985eff32", size = 952055, upload-time = "2026-03-19T14:22:25.026Z" }
<     { url = "https://files.pythonhosted.org/packages/3a/2a/7cc015f5b9f5db42b7d48157e23356022889fc354a2813c15934b7cb5c0e/attrs-25.4.0-py3-none-any.whl", hash = "sha256:adcf7e2a1fb3b36ac48d97835bb6d8ade15b8dcce26aba8bf1d14847b57a3373", size = 67615, upload-time = "2025-10-06T13:54:43.17Z" },
>     { url = "https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl", hash = "sha256:c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309", size = 67548, upload-time = "2026-03-19T14:22:23.645Z" },
< version = "2.17.0"
> version = "2.18.0"
< sdist = { url = "https://files.pythonhosted.org/packages/7d/6b/d52e42361e1aa00709585ecc30b3f9684b3ab62530771402248b1b1d6240/babel-2.17.0.tar.gz", hash = "sha256:0c54cffb19f690cdcc52a3b50bcbf71e07a808d1c80d549f2459b9d2cf0afb9d", size = 9951852, upload-time = "2025-02-01T15:17:41.026Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/7d/b2/51899539b6ceeeb420d40ed3cd4b7a40519404f9baf3d4ac99dc413a834b/babel-2.18.0.tar.gz", hash = "sha256:b80b99a14bd085fcacfa15c9165f651fbb3406e66cc603abf11c5750937c992d", size = 9959554, upload-time = "2026-02-01T12:30:56.078Z" }
<     { url = "https://files.pythonhosted.org/packages/b7/b8/3fe70c75fe32afc4bb507f75563d39bc5642255d1d94f1f23604725780bf/babel-2.17.0-py3-none-any.whl", hash = "sha256:4d0b53093fdfb4b21c92b5213dba5a1b23885afa8383709427046b21c366e5f2", size = 10182537, upload-time = "2025-02-01T15:17:37.39Z" },
>     { url = "https://files.pythonhosted.org/packages/77/f5/21d2de20e8b8b0408f0681956ca2c69f1320a3848ac50e6e7f39c6159675/babel-2.18.0-py3-none-any.whl", hash = "sha256:e2b422b277c2b9a9630c1d7903c2a00d0830c409c59ac8cae9081c92f1aeba35", size = 10196845, upload-time = "2026-02-01T12:30:53.445Z" },
< version = "4.14.2"
> version = "4.14.3"
< sdist = { url = "https://files.pythonhosted.org/packages/77/e9/df2358efd7659577435e2177bfa69cba6c33216681af51a707193dec162a/beautifulsoup4-4.14.2.tar.gz", hash = "sha256:2a98ab9f944a11acee9cc848508ec28d9228abfd522ef0fad6a02a72e0ded69e", size = 625822, upload-time = "2025-09-29T10:05:42.613Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/c3/b0/1c6a16426d389813b48d95e26898aff79abbde42ad353958ad95cc8c9b21/beautifulsoup4-4.14.3.tar.gz", hash = "sha256:6292b1c5186d356bba669ef9f7f051757099565ad9ada5dd630bd9de5fa7fb86", size = 627737, upload-time = "2025-11-30T15:08:26.084Z" }
<     { url = "https://files.pythonhosted.org/packages/94/fe/3aed5d0be4d404d12d36ab97e2f1791424d9ca39c2f754a6285d59a3b01d/beautifulsoup4-4.14.2-py3-none-any.whl", hash = "sha256:5ef6fa3a8cbece8488d66985560f97ed091e22bbc4e9c2338508a9d5de6d4515", size = 106392, upload-time = "2025-09-29T10:05:43.771Z" },
>     { url = "https://files.pythonhosted.org/packages/1a/39/47f9197bdd44df24d67ac8893641e16f386c984a0619ef2ee4c51fbbc019/beautifulsoup4-4.14.3-py3-none-any.whl", hash = "sha256:0918bfe44902e6ad8d57732ba310582e98da931428d231a5ecb9e7c703a735bb", size = 107721, upload-time = "2025-11-30T15:08:24.087Z" },
< version = "2025.11.12"
> version = "2026.4.22"
< sdist = { url = "https://files.pythonhosted.org/packages/a2/8c/58f469717fa48465e4a50c014a0400602d3c437d7c0c468e17ada824da3a/certifi-2025.11.12.tar.gz", hash = "sha256:d8ab5478f2ecd78af242878415affce761ca6bc54a22a27e026d7c25357c3316", size = 160538, upload-time = "2025-11-12T02:54:51.517Z" }
> sdist = { url = "https://files.pythonhosted.org/packages/25/ee/6caf7a40c36a1220410afe15a1cc64993a1f864871f698c0f93acb72842a/certifi-2026.4.22.tar.gz", hash = "sha256:8d455352a37b71bf76a79caa83a3d6c25afee4a385d632127b6afb3963f1c580", size = 137077, upload-time = "2026-04-22T11:26:11.191Z" }
<     { url = "https://files.pythonhosted.org/packages/70/7d/9bc192684cea499815ff478dfcdc13835ddf401365057044fb721ec6bddb/certifi-2025.11.12-py3-none-any.whl", hash = "sha256:97de8790030bbd5c2d96b7ec782fc2f7820ef8dba6db909ccf95449f2d062d4b", size = 159438, upload-time = "2025-11-12T02:54:49.735Z" },
```
