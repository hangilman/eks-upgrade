# v1.31.1

- patch note

# v1.31.0

## Changelog since v1.30.0

## Urgent Upgrade Notes 

### (No, really, you MUST read this before you upgrade)

- Added support to the scheduler to start using QueueingHint registered for Pod/Updated event to determine whether unschedulable Pods update make them schedulable, when the feature gate `SchedulerQueueingHints` is enabled.
  Previously, when unschedulable Pods are updated, the scheduler always put Pods back to activeQ/backoffQ. But, actually not all updates to Pods make Pods schedulable, especially considering many scheduling constraints nowadays are immutable.
  Now, when unschedulable Pods are updated, the scheduling queue checks with QueueingHint(s) whether the update may make the pods schedulable, and requeues them to activeQ/backoffQ **only when** at least one QueueingHint(s) return Queue. 
  
  Action required for custom scheduler plugin developers:
  Plugins **have to** implement a QueueingHint for Pod/Update event if the rejection from them could be resolved by updating unscheduled Pods themselves.
  Example: suppose you develop a custom plugin that denies Pods that have a `schedulable=false` label. 
  Given Pods with a `schedulable=false` label will be schedulable if the `schedulable=false` label is removed, this plugin would implement QueueingHint for Pod/Update event that returns Queue when such label changes are made in unscheduled Pods. ([#122234](https://github.com/kubernetes/kubernetes/pull/122234), [@AxeZhan](https://github.com/AxeZhan)) [SIG Scheduling and Testing]
 - Kubelet flag `--keep-terminated-pod-volumes` was removed.  This flag was deprecated in 2017. ([#122082](https://github.com/kubernetes/kubernetes/pull/122082), [@carlory](https://github.com/carlory)) [SIG Apps, Node, Storage and Testing]
 - Reduced state change noise when volume expansion fails. Also mark certain failures as infeasible.
  
  ACTION REQUIRED:  If you are using the `RecoverVolumeExpansionFailure` alpha feature gate
  then after upgrading to this release, you need to update some objects.
  For any existing PersistentVolumeClaimss with `status.allocatedResourceStatus` set to either
  "ControllerResizeFailed" or "NodeResizeFailed", clear the `status.allocatedResourceStatus`. ([#126108](https://github.com/kubernetes/kubernetes/pull/126108), [@gnufied](https://github.com/gnufied)) [SIG Apps, Auth, Node, Storage and Testing]
 
## Changes by Kind

### Deprecation

- 'kubeadm: marked the sub-phase of ''init kubelet-finilize'' called ''experimental-cert-rotation''
  as deprecated and print a warning if it is used directly; it will be removed in
  a future release. Add a replacement sub-phase ''enable-client-cert-rotation''.' ([#124419](https://github.com/kubernetes/kubernetes/pull/124419), [@neolit123](https://github.com/neolit123)) [SIG Cluster Lifecycle]
- Added a warning when creating or updating a PersistentVolume (PV) with the deprecated annotation `volume.beta.kubernetes.io/mount-options`. ([#124819](https://github.com/kubernetes/kubernetes/pull/124819), [@carlory](https://github.com/carlory))
- CephFS volume plugin ( `kubernetes.io/cephfs`) was removed in this release and the `cephfs` volume type became non-functional. Alternative is to use CephFS CSI driver (https://github.com/ceph/ceph-csi/) in your Kubernetes Cluster. A re-deployment of your application is required to use the new driver if you were using `kubernetes.io/cephfs` volume plugin before upgrading cluster version to 1.31+. ([#124544](https://github.com/kubernetes/kubernetes/pull/124544), [@carlory](https://github.com/carlory)) [SIG Node, Scalability, Storage and Testing]
- CephRBD volume plugin ( `kubernetes.io/rbd`) was removed in this release. And its csi migration support was also removed, so the `rbd` volume type became non-functional. Alternative is to use RBD CSI driver (https://github.com/ceph/ceph-csi/) in your Kubernetes Cluster. A re-deployment of your application is required to use the new driver if you were using `kubernetes.io/rbd` volume plugin before upgrading cluster version to 1.31+. ([#124546](https://github.com/kubernetes/kubernetes/pull/124546), [@carlory](https://github.com/carlory)) [SIG Node, Scalability, Scheduling, Storage and Testing]
- Kube-scheduler deprecated all non-csi volumelimit plugins and removed those from defaults plugins. 
  - AzureDiskLimits
  - CinderLimits
  - EBSLimits
  - GCEPDLimits
  
  The NodeVolumeLimits plugin can handle the same functionality as the above plugins since the above volume types are migrated to CSI.
  Please remove those plugins and replace them with the NodeVolumeLimits plugin if you explicitly use those plugins in the scheduler config.
  Those plugins will be removed in the release 1.32. ([#124500](https://github.com/kubernetes/kubernetes/pull/124500), [@carlory](https://github.com/carlory)) [SIG Scheduling and Storage]
- Kubeadm: deprecated the kubeadm `RootlessControlPlane` feature gate (previously alpha), given that the core K8s `UserNamespacesSupport` feature gate graduated to beta in 1.30.
  Once core Kubernetes support for user namespaces is generally available and kubeadm has started to support running the control plane in userns pods, the kubeadm `RootlessControlPlane` feature gate will be removed entirely.
  Until kubeadm supports the userns functionality out of the box, users can continue using the deprecated  `RootlessControlPlane` feature gate, or  opt-in `UserNamespacesSupport` by using kubeadm patches on the static pod manifests. ([#124997](https://github.com/kubernetes/kubernetes/pull/124997), [@neolit123](https://github.com/neolit123)) [SIG Cluster Lifecycle]
- Removed k8s.io/legacy-cloud-providers from staging. ([#124767](https://github.com/kubernetes/kubernetes/pull/124767), [@carlory](https://github.com/carlory)) [SIG API Machinery, Cloud Provider and Release]
- Removed legacy cloud provider integration code (undoing a previous reverted commit). ([#124886](https://github.com/kubernetes/kubernetes/pull/124886), [@carlory](https://github.com/carlory)) [SIG Cloud Provider and Release]

### API Change

- 'ACTION REQUIRED: The Dynamic Resource Allocation (DRA) driver's DaemonSet
  must be deployed with a service account that enables writing ResourceSlice
  and reading ResourceClaim objects.'
   ([#125163](https://github.com/kubernetes/kubernetes/pull/125163), [@pohly](https://github.com/pohly)) [SIG Auth, Node and Testing]
- Add UserNamespaces field to NodeRuntimeHandlerFeatures ([#126034](https://github.com/kubernetes/kubernetes/pull/126034), [@sohankunkerkar](https://github.com/sohankunkerkar)) [SIG API Machinery, Apps and Node]
- Added Coordinated Leader Election as Alpha under the `CoordinatedLeaderElection` feature gate. With the feature enabled, the control plane can use LeaseCandidate objects (coordination.k8s.io/v1alpha1 API group) to participate in a leader election and let the kube-apiserver select the best instance according to some strategy. ([#124012](https://github.com/kubernetes/kubernetes/pull/124012), [@Jefftree](https://github.com/Jefftree)) [SIG API Machinery, Apps, Auth, Cloud Provider, Etcd, Node, Release, Scheduling and Testing]
- Added a `.status.features.supplementalGroupsPolicy` field to Nodes. The field is true when the feature is implemented in the CRI implementation (KEP-3619). ([#125470](https://github.com/kubernetes/kubernetes/pull/125470), [@everpeace](https://github.com/everpeace)) [SIG API Machinery, Apps, Node and Testing]
- Added an `allocatedResourcesStatus` to each container status to indicate the health status of devices exposed by the device plugin. ([#126243](https://github.com/kubernetes/kubernetes/pull/126243), [@SergeyKanzhelev](https://github.com/SergeyKanzhelev)) [SIG API Machinery, Apps, Node and Testing]
- Added support to the kube-proxy nodePortAddresses / --nodeport-addresses option to
  accept the value "primary", meaning to only listen for NodePort connections
  on the node's primary IPv4 and/or IPv6 address (according to the Node object).
  This is strongly recommended, if you were not previously using
  --nodeport-addresses, to avoid surprising behavior.
  (This behavior is enabled by default with the nftables backend; you would
  need to explicitly request `--nodeport-addresses 0.0.0.0/0,::/0` there to get
  the traditional "listen on all interfaces" behavior.) ([#123105](https://github.com/kubernetes/kubernetes/pull/123105), [@danwinship](https://github.com/danwinship)) [SIG API Machinery, Network and Windows]
- Added the feature gates `StrictCostEnforcementForVAP` and `StrictCostEnforcementForWebhooks` to enforce the strict cost calculation for CEL extended libraries. It is strongly recommended to turn on the feature gates as early as possible. ([#124675](https://github.com/kubernetes/kubernetes/pull/124675), [@cici37](https://github.com/cici37)) [SIG API Machinery, Auth, Node and Testing]
- Changed how the API server handles updates to `.spec.defaultBackend` of Ingress objects.
  Server-side apply now considers `.spec.defaultBackend` to be an atomic struct.  This means that any field-owner who sets values in that struct (they are mutually exclusive) owns the whole struct. For almost all users this change has no impact; for controllers that want to change the default backend port from number to name (or vice-versa), this makes it easier. ([#126207](https://github.com/kubernetes/kubernetes/pull/126207), [@thockin](https://github.com/thockin)) [SIG API Machinery]
- Component-base/logs: when compiled with Go >= 1.21, component-base will automatically configure the slog default logger together with initializing klog. ([#120696](https://github.com/kubernetes/kubernetes/pull/120696), [@pohly](https://github.com/pohly)) [SIG API Machinery, Architecture, Auth, CLI, Cloud Provider, Cluster Lifecycle, Instrumentation, Network, Storage and Testing]
- CustomResourceDefinition objects created with non-empty `caBundle` fields which are invalid or do not contain any certificates will not appear in discovery or serve endpoints until a valid `caBundle` is provided. Updates to CustomResourceDefinition are no longer allowed to transition a valid `caBundle` field to an invalid `caBundle` field, because this breaks serving of the existing CustomResourceDefinition. ([#124061](https://github.com/kubernetes/kubernetes/pull/124061), [@Jefftree](https://github.com/Jefftree)) [SIG API Machinery]
- Dynamic Resource Allocation (DRA): Added a feature so the number of ResourceClaim objects can be limited per namespace and by the number of devices requested through a specific class via the v1.ResourceQuota mechanism. ([#120611](https://github.com/kubernetes/kubernetes/pull/120611), [@pohly](https://github.com/pohly)) [SIG API Machinery, Apps, Auth, CLI, Etcd, Node, Release, Scheduling and Testing]
- Dynamic Resource Allocation (DRA): client-side validation of a ResourceHandle would have accepted a missing DriverName, whereas server-side validation then would have raised an error. ([#124075](https://github.com/kubernetes/kubernetes/pull/124075), [@pohly](https://github.com/pohly))
- Dynamic Resource Allocation (DRA): in the `pod.spec.recourceClaims` array, the `source` indirection is no longer necessary. Instead of e.g. `source: resourceClaimTemplateName: my-template`, one can write `resourceClaimTemplateName: my-template`. ([#125116](https://github.com/kubernetes/kubernetes/pull/125116), [@pohly](https://github.com/pohly)) [SIG API Machinery, Apps, Auth, Node, Scheduling and Testing]
- Enhanced the Dynamic Resource Allocation (DRA) with an updated version of the resource.k8s.io API group. The primary user-facing type remains the ResourceClaim, however significant changes have been made, resulting in the new version, v1alpha3, which is not compatible with the previous version. ([#125488](https://github.com/kubernetes/kubernetes/pull/125488), [@pohly](https://github.com/pohly)) [SIG API Machinery, Apps, Auth, CLI, Cluster Lifecycle, Etcd, Node, Release, Scheduling, Storage and Testing]
- Fixed a 1.30.0 regression in OpenAPI descriptions of the `imagePullSecrets` and 
  `hostAliases` fields to mark the fields used as keys in those lists as either defaulted
  or required. ([#124553](https://github.com/kubernetes/kubernetes/pull/124553), [@pmalek](https://github.com/pmalek))
- Fixed a 1.30.0 regression in openapi descriptions of `PodIP.IP`  and `HostIP.IP` fields to mark the fields used as keys in those lists as required. ([#126057](https://github.com/kubernetes/kubernetes/pull/126057), [@thockin](https://github.com/thockin))
- Fixed a bug in the API server where empty collections of ValidatingAdmissionPolicies did not have an `items` field. ([#124568](https://github.com/kubernetes/kubernetes/pull/124568), [@xyz-li](https://github.com/xyz-li)) [SIG API Machinery]
- Fixed a deep copy issue when retrieving the controller reference. ([#124116](https://github.com/kubernetes/kubernetes/pull/124116), [@HiranmoyChowdhury](https://github.com/HiranmoyChowdhury)) [SIG API Machinery and Release]
- Fixed code-generator client-gen to work with `api/v1`-like package structure. ([#125162](https://github.com/kubernetes/kubernetes/pull/125162), [@sttts](https://github.com/sttts)) [SIG API Machinery and Apps]
- Fixed incorrect "v1 Binding is deprecated in v1.6+" warning in kube-scheduler log. ([#125540](https://github.com/kubernetes/kubernetes/pull/125540), [@pohly](https://github.com/pohly)) [SIG API Machinery]
- Fixed the comment for the Job's managedBy field. ([#124793](https://github.com/kubernetes/kubernetes/pull/124793), [@mimowo](https://github.com/mimowo)) [SIG API Machinery and Apps]
- Fixed the documentation for the default value of the `procMount` entry in `securityContext` within a Pod.
  The documentation was previously using the name of the internal variable `DefaultProcMount`, rather than the actual value, "Default". ([#125782](https://github.com/kubernetes/kubernetes/pull/125782), [@aborrero](https://github.com/aborrero)) [SIG Apps and Node]
- Graduate PodDisruptionConditions to GA and lock ([#125461](https://github.com/kubernetes/kubernetes/pull/125461), [@mimowo](https://github.com/mimowo)) [SIG Apps, Node, Scheduling and Testing]
- Graduated MatchLabelKeys/MismatchLabelKeys feature in PodAffinity/PodAntiAffinity to Beta. ([#123638](https://github.com/kubernetes/kubernetes/pull/123638), [@sanposhiho](https://github.com/sanposhiho)) [SIG API Machinery, Apps, Scheduling and Testing]
- Graduated `JobPodFailurePolicy` to GA and locked it to it's default. ([#125442](https://github.com/kubernetes/kubernetes/pull/125442), [@mimowo](https://github.com/mimowo)) [SIG API Machinery, Apps, Scheduling and Testing]
- Graduated the Job `successPolicy` field to beta.
  
  The new reason label, "SuccessPolicy" and "CompletionsReached" are added to the "jobs_finished_total" metric.
  Additionally, if you enable the `JobSuccessPolicy` feature gate, the Job gets "CompletionsReached" reason for the "SuccessCriteriaMet" and "Complete" condition type
  when the number of succeeded Job Pods (`.status.succeeded`) reached the desired completions (`.spec.completions`). ([#126067](https://github.com/kubernetes/kubernetes/pull/126067), [@tenzen-y](https://github.com/tenzen-y)) [SIG API Machinery, Apps and Testing]
- Graduated the `DisableNodeKubeProxyVersion` feature gate to beta. By default, the kubelet no longer attempts to set the `.status.kubeProxyVersion` field for its associated Node. ([#123845](https://github.com/kubernetes/kubernetes/pull/123845), [@HirazawaUi](https://github.com/HirazawaUi)) [SIG API Machinery, Cloud Provider, Network, Node and Testing]
- Improved scheduling performance when many nodes, and prefilter returned 1-2 nodes (e.g. daemonset)
  
  For developers of out-of-tree PostFilter plugins, note that the semantics of NodeToStatusMap are changing: A node with an absent value in the NodeToStatusMap should be interpreted as having an UnschedulableAndUnresolvable status. ([#125197](https://github.com/kubernetes/kubernetes/pull/125197), [@gabesaba](https://github.com/gabesaba))
- Introduced a new boolean kubelet flag `--fail-cgroupv1`. ([#126031](https://github.com/kubernetes/kubernetes/pull/126031), [@harche](https://github.com/harche)) [SIG API Machinery and Node]
- K8s.io/apimachinery/pkg/util/runtime: Added support for new calls to handle panics and errors in the context where they occur. `PanicHandlers` and `ErrorHandlers` now must accept a context parameter for that. Log output is structured instead of unstructured. ([#121970](https://github.com/kubernetes/kubernetes/pull/121970), [@pohly](https://github.com/pohly)) [SIG API Machinery and Instrumentation]
- KEP-1880: Users of the new feature to add multiple service CIDR will use by default a dual-write strategy on the new ClusterIP allocators to avoid the problem of possible duplicate IPs allocated to Services when running skewed kube-apiservers using different allocators. They can opt-out of this behavior by enabled the feature gate DisableAllocatorDualWrite. ([#122047](https://github.com/kubernetes/kubernetes/pull/122047), [@aojea](https://github.com/aojea)) [SIG API Machinery, Apps, Instrumentation and Testing]
- Kube-apiserver: Added Alpha features to allow API server authz to check the context of requests:
  - The `AuthorizeWithSelectors` feature gate enables including field and label selector information from requests in webhook authorization calls.
  - The `AuthorizeNodeWithSelectors` feature gate changes node authorizer behavior to limit requests from node API clients, so that each Node can only get / list / watch its own Node API object, and can also only get / list / watch Pod API objects bound to that node. Clients using kubelet credentials to read other nodes or unrelated pods must change their authentication credentials (recommended), adjust their usage, or obtain broader read access independent of the node authorizer. ([#125571](https://github.com/kubernetes/kubernetes/pull/125571), [@liggitt](https://github.com/liggitt)) [SIG API Machinery, Auth, Node, Scheduling and Testing]
- Kube-apiserver: ControllerRevision objects are now verified to contain valid JSON data in the `data` field. ([#125549](https://github.com/kubernetes/kubernetes/pull/125549), [@liggitt](https://github.com/liggitt)) [SIG API Machinery and Apps]
- Kube-apiserver: the `--encryption-provider-config` file is now loaded with strict deserialization, which fails if the config file contains duplicate or unknown fields. This protects against accidentally running with config files that are malformed, mis-indented, or have typos in field names, and getting unexpected behavior. When `--encryption-provider-config-automatic-reload` is used, new encryption config files that contain typos after the kube-apiserver is running are treated as invalid and the last valid config is used. ([#124912](https://github.com/kubernetes/kubernetes/pull/124912), [@enj](https://github.com/enj)) [SIG API Machinery and Auth]
- Kube-controller-manager: the `horizontal-pod-autoscaler-upscale-delay` and `horizontal-pod-autoscaler-downscale-delay` flags have been removed (deprecated and non-functional since v1.12). ([#124948](https://github.com/kubernetes/kubernetes/pull/124948), [@SataQiu](https://github.com/SataQiu)) [SIG API Machinery, Apps and Autoscaling]
- Made kube-proxy Windows service control manager integration (`--windows-service`) configurable in v1alpha1 component configuration via `windowsRunAsService` field. ([#126072](https://github.com/kubernetes/kubernetes/pull/126072), [@aroradaman](https://github.com/aroradaman)) [SIG Network and Scalability]
- PersistentVolumeLastPhaseTransitionTime feature is stable and enabled by default. ([#124969](https://github.com/kubernetes/kubernetes/pull/124969), [@RomanBednar](https://github.com/RomanBednar)) [SIG API Machinery, Apps, Storage and Testing]
- Promoted `LocalStorageCapacityIsolation` to beta; the behaviour is enabled by default. Within the kubelet, storage capacity isolation is active if the feature gate is enabled and the specific Pod is using a user namespace. ([#126014](https://github.com/kubernetes/kubernetes/pull/126014), [@PannagaRao](https://github.com/PannagaRao)) [SIG Apps, Autoscaling, Node, Storage and Testing]
- Promoted `StatefulSetStartOrdinal` to stable. This means `--feature-gates=StatefulSetStartOrdinal=true` are not needed on kube-apiserver and kube-controller-manager binaries and they'll be removed soon following policy at https://kubernetes.io/docs/reference/using-api/deprecation-policy/#deprecation. ([#125374](https://github.com/kubernetes/kubernetes/pull/125374), [@pwschuurman](https://github.com/pwschuurman)) [SIG API Machinery, Apps and Testing]
- Promoted feature-gate `VolumeAttributesClass` to beta (disabled by default). Users need to enable the feature gate and the `storage.k8s.io/v1beta1` API group to use this feature.
  Promoted the VolumeAttributesClass API to beta. ([#126145](https://github.com/kubernetes/kubernetes/pull/126145), [@carlory](https://github.com/carlory)) [SIG API Machinery, Apps, CLI, Etcd, Storage and Testing]
- Removed deprecated command flags --volume-host-cidr-denylist
  and --volume-host-allow-local-loopback from kube-controller-manager.
   ([#124017](https://github.com/kubernetes/kubernetes/pull/124017), [@carlory](https://github.com/carlory)) [SIG API Machinery, Apps, Cloud Provider and Storage]
- Removed feature gate `CustomResourceValidationExpressions`. ([#126136](https://github.com/kubernetes/kubernetes/pull/126136), [@cici37](https://github.com/cici37)) [SIG API Machinery, Cloud Provider and Testing]
- Reverted a [change](https://github.com/kubernetes/kubernetes/pull/123513) where `ConsistentListFromCache` was moved to beta and enabled by default. ([#126139](https://github.com/kubernetes/kubernetes/pull/126139), [@enj](https://github.com/enj))
- Revised the Pod API with Alpha support for volumes derived from OCI artifacts. This feature is behind the `ImageVolume` feature gate. ([#125660](https://github.com/kubernetes/kubernetes/pull/125660), [@saschagrunert](https://github.com/saschagrunert)) [SIG API Machinery, Apps and Node]
- Supported fine-grained supplemental groups policy (KEP-3619), which enabled
  fine-grained control for supplementary groups in the first container processes.
  This allows you to choose whether to include groups defined in the container image (/etc/groups)
  for the container's primary UID or not. ([#117842](https://github.com/kubernetes/kubernetes/pull/117842), [@everpeace](https://github.com/everpeace)) [SIG API Machinery, Apps and Node]
- The (alpha) nftables mode of kube-proxy now requires version 1.0.1 or later
  of the nft command-line, and kernel 5.13 or later. (For testing/development
  purposes, you can use older kernels, as far back as 5.4, if you set the
  `nftables.skipKernelVersionCheck` option in the kube-proxy config, but this is not
  recommended in production since it may cause problems with other nftables
  users on the system.) ([#124152](https://github.com/kubernetes/kubernetes/pull/124152), [@danwinship](https://github.com/danwinship)) [SIG Network]
- To enhance usability and developer experience, CRD validation rules now support direct use of (CEL) reserved keywords as field names in object validation expressions for existing expressions in storage, will fully support runtime in next release for compatibility concern. ([#126188](https://github.com/kubernetes/kubernetes/pull/126188), [@cici37](https://github.com/cici37)) [SIG API Machinery and Testing]
- Updated the feature MultiCIDRServiceAllocator to beta (disabled by default). Users need to enable the feature gate and the networking v1beta1 group to be able to use this new feature, that allows to dynamically reconfigure Service CIDR ranges. ([#125021](https://github.com/kubernetes/kubernetes/pull/125021), [@aojea](https://github.com/aojea)) [SIG API Machinery, Apps, CLI, Etcd, Instrumentation, Network and Testing]
- Use omitempty for optional Job Pod Failure Policy fields. ([#126046](https://github.com/kubernetes/kubernetes/pull/126046), [@mimowo](https://github.com/mimowo))
- User can choose a different static policy option `SpreadPhysicalCPUsPreferredOption` to spread cpus across physical cpus for some specific applications ([#123733](https://github.com/kubernetes/kubernetes/pull/123733), [@Jeffwan](https://github.com/Jeffwan)) [SIG Node]
- When the featuregate AnonymousAuthConfigurableEndpoints is enabled users can update the AuthenticationConfig file with endpoints for with anonymous requests are alllowed. ([#124917](https://github.com/kubernetes/kubernetes/pull/124917), [@vinayakankugoyal](https://github.com/vinayakankugoyal)) [SIG API Machinery, Auth, Cloud Provider, Node and Testing]


## Dependencies

# v1.31.0-rc.1

- rc note

