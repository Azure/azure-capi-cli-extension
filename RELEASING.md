# How to Create an "az capi" Release

1. **Check out code at the correct commit.**

    Currently this project releases from the `main` branch. Make sure your local copy of the code is up to date:

    ```shell
    git checkout main
    git pull
    ```

2. **Choose the next semantic version.**

    In the pre-release phase, all releases are patches. Choose the next patch version, such as `v0.0.6`:

    ```shell
    git describe --tags --abbrev=0
    export RELEASE_VERSION=v0.0.6
    ```

3. **Verify that setup.py references the new version.**

    In the file [src/capi/setup.py](./src/capi/setup.py), set `VERSION` to the new version and save the file.

4. **Update HISTORY.rst with release notes for the new version.**

    In the file [src/capi/HISTORY.rst](./src/capi/setup.py), add a section for the new version with a short summary of the important changes. Save the file and `git commit` both `HISTORY.rst` and `setup.py` from the previous step.

    ```shell
    git add src/capi/HISTORY.rst src/capi/setup.py
    git commit -m "Update HISTORY.rst and setup.py for ${RELEASE_VERSION}"
    ```

5. **Tag the code and push it upstream.**

    ```shell
    git push upstream main
    git tag -a $RELEASE_VERSION -m "Release $RELEASE_VERSION"
    git push upstream $RELEASE_VERSION
    ```

6. **Wait for the GitHub action to create a draft release.**

    A [GitHub Action](https://github.com/Azure/azure-capi-cli-extension/actions) will run against the release tag. When it completes, it will create [a draft release](https://github.com/Azure/azure-capi-cli-extension/releases).

7. **Update the draft release and publish it.**

    Follow the general format of previous release notes, starting with a high-level summary of user-facing changes.

    If the release notes reference merge commits authored by a bot, click through to the original PR, then update the reference so that the actual author is credited.

    Once you are satisfied with your changes, publish the release so it's no longer a draft. Leave the "pre-release" checkbox checked until `az capi` reaches v1.0.

8. **Publicize the release.**

    Announce the new release on the [CAPZ Slack channel](https://kubernetes.slack.com/archives/CEX9HENG7).
