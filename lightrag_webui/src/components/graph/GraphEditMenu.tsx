import { useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { createEntity, createRelation, mergeEntities, deleteEntity, deleteRelation } from '@/api/lightrag'

const DEFAULT_MERGE_STRATEGY = {
  description: 'concatenate',
  entity_type: 'keep_first',
  source_id: 'join_unique'
}
import { useGraphStore } from '@/stores/graph'

const GraphEditMenu = () => {
  const multiSelectedNodes = useGraphStore.use.multiSelectedNodes()
  const clearMultiSelectedNodes = useGraphStore.use.clearMultiSelectedNodes()
  const selectedNode = useGraphStore.use.selectedNode()
  const selectedEdge = useGraphStore.use.selectedEdge()
  const rawGraph = useGraphStore.use.rawGraph()

  const [nodeName, setNodeName] = useState('')
  const [nodeData, setNodeData] = useState('{}')

  const [relSource, setRelSource] = useState('')
  const [relTarget, setRelTarget] = useState('')
  const [relData, setRelData] = useState('{}')

  const handleCreateNode = async () => {
    try {
      await createEntity(nodeName, JSON.parse(nodeData))
      setNodeName('')
      setNodeData('{}')
    } catch (e) {
      console.error(e)
    }
  }

  const handleCreateRelation = async () => {
    try {
      await createRelation(relSource, relTarget, JSON.parse(relData))
      setRelSource('')
      setRelTarget('')
      setRelData('{}')
    } catch (e) {
      console.error(e)
    }
  }

  const handleMerge = async () => {
    if (multiSelectedNodes.length < 2) return
    const [target, ...sources] = multiSelectedNodes
    try {
      await mergeEntities(sources, target, DEFAULT_MERGE_STRATEGY)
    } catch (e) {
      console.error(e)
    }
    clearMultiSelectedNodes()
  }

  const handleDeleteNode = async () => {
    if (!selectedNode) return
    try {
      await deleteEntity(selectedNode)
    } catch (e) {
      console.error(e)
    }
  }

  const handleDeleteRelation = async () => {
    if (!selectedEdge || !rawGraph) return
    const edge = rawGraph.getEdge(selectedEdge, true)
    if (!edge) return
    try {
      await deleteRelation(edge.source, edge.target)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="bg-background/60 absolute top-24 left-2 flex flex-col gap-2 rounded-xl border-2 p-2 text-xs backdrop-blur-lg">
      {multiSelectedNodes.length > 1 && (
        <div className="flex flex-col gap-1">
          <div>Selected nodes:</div>
          <ul className="list-disc list-inside">
            {multiSelectedNodes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          <Button size="sm" onClick={handleMerge}>Merge Nodes</Button>
        </div>
      )}
      {selectedNode && (
        <Button size="sm" variant="destructive" onClick={handleDeleteNode}>
          Delete Node
        </Button>
      )}
      {selectedEdge && (
        <Button size="sm" variant="destructive" onClick={handleDeleteRelation}>
          Delete Relation
        </Button>
      )}
      <div className="flex flex-col gap-1 pt-1 border-t mt-1">
        <Input placeholder="Node name" value={nodeName} onChange={(e) => setNodeName(e.target.value)} />
        <Input placeholder="Node data JSON" value={nodeData} onChange={(e) => setNodeData(e.target.value)} />
        <Button size="sm" onClick={handleCreateNode}>Create Node</Button>
      </div>
      <div className="flex flex-col gap-1 pt-1 border-t mt-1">
        <Input placeholder="Source" value={relSource} onChange={(e) => setRelSource(e.target.value)} />
        <Input placeholder="Target" value={relTarget} onChange={(e) => setRelTarget(e.target.value)} />
        <Input placeholder="Relation data JSON" value={relData} onChange={(e) => setRelData(e.target.value)} />
        <Button size="sm" onClick={handleCreateRelation}>Create Relation</Button>
      </div>
    </div>
  )
}

export default GraphEditMenu
