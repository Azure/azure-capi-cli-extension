goals

- Make using Cluster API in Azure as simple as possible
  - automate initial setup
  - `az capi` verbs handle workload clusters, the more frequently used commands
  - `az capi management` verbs handle management clusters, hopefully rarely used commands
  - provision a managment cluster just-in-time if needed, then don't mention it again
  - Have opinionated defaults so few options are required
  - follow az CLI standards as much as possible (for example, use REST-ish verbs)
- Enable flexible definition of CAPZ resources and features
  - allow mix-and-match of major features, for example "GPU-enabled with IPV6"
  - provision just a control plane, then attach node pools later as a separate step
- Extend the reach of CAPZ toward non-expert users
  - lower the entry bar for installation to just "az extension install <url>"
  - assume the user will just blunder into `az capi create`, so that should start
    interactive setup if needed
  - make the templating system obvious and approachable so others can modify
  - save local manifests in a hierarchy that illustrates their relationships
  - support "kind" or "aks" or "existing" for management cluster creation
  - use great error and help messages to educate users about CAPI
  - link to the CAPI or CAPZ book from error and help messages
- Embody "best practices" for CAPI on Azure
  - support git ops or a "git flow" workflow for declarative cluster lifecycle
  - use AAD Pod ID by default, avoid requiring AZURE_foo env vars
