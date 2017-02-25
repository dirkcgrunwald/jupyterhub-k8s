#/usr/bin/python3

"""Provides read and write access to Kubernetes API"""

from kubernetes import client, config
import logging

from utils import get_pod_host_name, get_pod_type, get_node_memory_capacity, check_list_intersection

scale_logger = logging.getLogger("scale")
logging.getLogger("kubernetes").setLevel(logging.WARNING)


class k8s_control:

    """Provides read and write access to Kubernetes API,
    and environment settings, including goals for the
    cluster always use the node and pods status at the
    time it was initiated

    self.pods do not contain pods required to be omitted 
    in settings"""

    def __init__(self, options):
        """ Needs to be initialized with options as an
        instance of settings"""
        config.load_kube_config()
        self.options = options
        self.v1 = client.CoreV1Api()
        self.nodes = self.get_nodes()
        self.pods = self.get_pods()  # See specs above
        self.critical_node_names = self.get_critical_node_names()
        self.critical_node_number = len(self.critical_node_names)

    def get_nodes(self):
        """Return a list of v1.Node"""
        scale_logger.debug("Getting all nodes in the cluster")
        return self.v1.list_node().items

    def get_pods(self):
        """Return a list of v1.Pod that needn't be omitted"""
        result = []
        scale_logger.debug("Getting all pods in all namespaces")
        pods = self.v1.list_pod_for_all_namespaces().items
        for pod in pods:
            if not (check_list_intersection(self.options.omit_labels, pod.metadata.labels) or pod.metadata.namespace in self.options.omit_namespaces):
                result.append(pod)
        return result

    def show_nodes_status(self):
        """Print the status of all nodes in the cluster"""
        print(
            "Node name \t\t Num of pods on node \t Schedulable? \t Preemptible?")
        for node in self.nodes:
            print("%s\t%i\t%s\t%s" %
                  (node.metadata.name,
                   self.get_pods_number_on_node(node),
                   "U" if node.spec.unschedulable else "S",
                   "N" if node.metadata.name in self.critical_node_names else "P"
                   ))

    def set_unschedulable(self, node_name, value=True):
        """Set the spec key 'unschedulable'"""
        scale_logger.debug(
            "Setting %s node's unschedulable property to %r", node_name, value)
        assert node_name not in self.critical_node_names
        new_node = client.V1Node(
            api_version="v1",
            kind="Node",
            metadata=client.V1ObjectMeta(name=node_name),
            spec=client.V1NodeSpec(unschedulable=value)
        )
        # TODO: exception handling
        self.v1.patch_node(node_name, new_node)

    def get_total_cluster_memory_usage(self):
        """Gets the total memory usage of 
        all student pods"""
        total_mem_usage = 0
        for pod in self.pods:
            try:
                total_mem_usage += int(
                    pod.spec.containers[0].resources.requests['memory'])
            except (KeyError, TypeError):
                # In the case that there is no memory request, the memory
                # usage is seen as 0
                continue
        return total_mem_usage

    def get_total_cluster_memory_capacity(self):
        """Returns the total memory capacity of all nodes, as student
        pods can be scheduled on any node that meets its Request criteria"""
        total_mem_capacity = 0
        critical_node_names = self.critical_node_names
        for node in self.nodes:
            if node.metadata.name not in critical_node_names:
                total_mem_capacity += get_node_memory_capacity(node)
        return total_mem_capacity

    def get_critical_node_names(self):
        """Return a list of nodes where critical pods
        are running"""
        result = []
        for pod in self.pods:
            if not check_list_intersection(pod.metadata.labels, self.options.preemptible_labels):
                if get_pod_host_name(pod) not in result:
                    result.append(get_pod_host_name(pod))
        return result

    def get_pods_number_on_node(self, node):
        """Return the effective number of pods on the node"""
        result = 0
        for pod in self.pods:
            if get_pod_host_name(pod) == node.metadata.name:
                result += 1
        return result

    def get_cluster_name(self):
        """Return the (guessed) name of the cluster"""
        node = self.nodes[0]
        node_name = node.metadata.name
        parts = node_name.split('-')
        assert len(parts) > 2
        return parts[1]

    def get_num_schedulable(self):
        """Return number of nodes schedulable AND NOT
        IN THE LIST OF CRITICAL NODES"""
        result = 0
        for node in self.nodes:
            if (not node.spec.unschedulable) and node.metadata.name not in self.critical_node_names:
                result += 1
        return result

    def get_num_unschedulable(self):
        """Return number of nodes unschedulable

        ASSUMING CRITICAL NODES ARE SCHEDULABLE"""
        result = 0
        for node in self.nodes:
            if node.spec.unschedulable:
                result += 1
        return result

if __name__ == "__main__":
    import settings
    k8s = k8s_control(settings.settings())
    print("Displaying information of cluster %s\n" % k8s.get_cluster_name())
    k8s.show_nodes_status()
    print("Current memory usage is %i" % k8s.get_total_cluster_memory_usage())
    print("Total memory capacity is %i, not including non-preemptible nodes" %
          k8s.get_total_cluster_memory_capacity())