# k8s-schema-merger

This is a CLI tool to help setting up Kubernetes schema linting with with [yamlls](https://github.com/redhat-developer/yaml-language-server).

## Motivation

Kubernetes manifest validation can be done by providing the corresponding
[schema definitions](https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/v1.22.4-standalone-strict/all.json)
to `yamlls`.
The same can be achieved for CRDs with one of the definitions from the [CRD catalog](https://github.com/datreeio/CRDs-catalog/).
However, this approach is insufficient when a file contains more than one
manifest with a combination of either different CRDs, or a CRDs with Kubernetes
primitives, given that `yamlls` is unable to validate one file with more than
one schema definition.

This tool provides a solution to this problem by merging the required
definitions into a single file.

## Usage

Install this Python module. E.g.:

```sh
pip install k8s-schema-merger
```

You can simply run `k8s-schema-merger` and let the module detect the Kubernetes
version and required CRD definitions by connecting to your Kubernetes cluster.

If cluster credentials are not available, or if you only want a subset of CRD
schemas, you can specify the version and required CRD groups yourself, like so:

```sh
k8s-schema-merger argoproj.io cert-manager.io k8s.nginx.org --version 1.32.0
```

The script will then download the schema definitions from the CRD catalog.
Note that these CRD groups must correspond with the names of top-level
directories from the CRD catalog.

You can also change the output directory with the `--output-dir` argument. By
default, all output files are stored in `$XDG_DATA_HOME/k8s-schema-merger`.

Also, you can always extend a previously generated schema definition with
additional CRDs by using the `--extend` argument.

## IDE setup

On nvim, adapt the `nvim-lspconfig` configuration to use the newly-generated
schemas for your Kubernetes manifests. Below is an example using
[lazy.nvim](https://github.com/folke/lazy.nvim).

```lua
{
  "neovim/nvim-lspconfig",
  opts = {
    servers = {
      yamlls = {
        settings = {
          yaml = {
            schemas = {
              ["file:/Users/whoever/.local/share/k8s-schema-merger/all.json"] = "k8s/*.y*ml",
            },
          },
        },
      },
    },
  },
}
```

## Caveats

The [yaml-language-server](https://github.com/redhat-developer/yaml-language-server)
project does not work with schemas other than those for Kubernetes v1.22.4,
which are [hard-coded](`https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/v1.22.4-standalone-strict/all.json`)
in its codebase.
In order to lint your manifests with custom schemas, you can patch your
installation of `yamlls` as shown in this patch:

```diff
index bec1f83..692d8ed 100644
--- a/settingsHandlers.js
+++ b/settingsHandlers.js
@@ -288,12 +288,12 @@ class SettingsHandler {
         else {
             languageSettings.schemas.push({ uri, fileMatch: fileMatch, schema: schema, priority: priorityLevel });
         }
-        if (fileMatch.constructor === Array && uri === schemaUrls_1.KUBERNETES_SCHEMA_URL) {
+        if (fileMatch.constructor === Array && (uri === schemaUrls_1.KUBERNETES_SCHEMA_URL || uri.search(/k8s-yaml-merger/))) {
             fileMatch.forEach((url) => {
                 this.yamlSettings.specificValidatorPaths.push(url);
             });
         }
-        else if (uri === schemaUrls_1.KUBERNETES_SCHEMA_URL) {
+        else if (uri === schemaUrls_1.KUBERNETES_SCHEMA_URL || uri.search(/k8s-yaml-merger/)) {
             this.yamlSettings.specificValidatorPaths.push(fileMatch);
         }
         return languageSettings;
```

If you installed `yamlls` with Mason, the aforementioned file may be located
at `~/.local/share/nvim/mason/packages/yaml-language-server/node_modules/yaml-language-server/out/server/src/languageserver/handlers/settingsHandlers.js`.
Remember to change the `/k8s-yaml-merger/` regex when using a different output
dir.

## Contributing

This project is a currently a functional proof of concept.
It can certainly be extended and improved, for example, by integrating the
generation of schemas directly in the IDE.

If you have ideas or comments about it, go ahead and open an issue to let me
know.
