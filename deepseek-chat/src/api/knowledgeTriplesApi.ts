/**
 * 知识三元组 API
 * ================
 * 
 * 调用后端 /api/knowledge/triples 相关端点
 */

import { apiGet } from './apiClient'

export interface Triple {
  id: number
  subject: string
  predicate: string
  object: string
}

export interface GraphData {
  triples: Triple[]
  concepts: string[]
  total: number
}

/**
 * 查询知识三元组
 */
export async function fetchTriples(params?: {
  subject?: string
  predicate?: string
  object?: string
  limit?: number
  offset?: number
}): Promise<{ data: Triple[]; total: number; limit: number; offset: number }> {
  const query = new URLSearchParams()
  if (params?.subject) query.set('subject', params.subject)
  if (params?.predicate) query.set('predicate', params.predicate)
  if (params?.object) query.set('object', params.object)
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.offset) query.set('offset', String(params.offset))

  const queryString = query.toString()
  return apiGet(`/knowledge/triples${queryString ? '?' + queryString : ''}`)
}

/**
 * 获取所有唯一实体
 */
export async function fetchSubjects(): Promise<string[]> {
  const response = await apiGet<{ success: boolean; data: string[] }>('/knowledge/subjects')
  return response.data
}

/**
 * 获取所有唯一关系
 */
export async function fetchPredicates(): Promise<string[]> {
  const response = await apiGet<{ success: boolean; data: string[] }>('/knowledge/predicates')
  return response.data
}

/**
 * 获取图数据（用于可视化）
 */
export async function fetchGraph(limit: number = 100): Promise<GraphData> {
  return apiGet(`/knowledge/graph?limit=${limit}`)
}
