import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useDeploymentCapabilitiesStore } from '@/stores/deploymentCapabilities'
import { managedSettingsSectionAllowed, usesManagedRuntime } from '@/config/managedRuntime'

export function useManagedRuntime() {
  const auth = useAuthStore()
  const deployment = useDeploymentCapabilitiesStore()
  const managed = computed(() => usesManagedRuntime(deployment.managedRuntime, auth.isSystemAdmin, deployment.loaded && !deployment.loadError))
  return {
    managed,
    canConfigureSection: (section: string) => managedSettingsSectionAllowed(section, managed.value),
  }
}
