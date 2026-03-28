export interface UserInfo {
  username: string
  display_name: string
  role: 'admin' | 'user'
}

export interface LinuxUser {
  name: string
  uid: number
  mem_gb: number
  proc_count: number
  cpu_percent: number
  groups: string[]
}

export interface UserQuota {
  key: string
  memory_gb: number
  max_processes: number
  cpu_cores: number
}
