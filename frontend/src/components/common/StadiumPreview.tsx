import { OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

// 3D preview of a stadium: the game's meshes and textures (GLB from the backend), lit only by the light the game baked
// into its "ambient" textures (a light map on the 2nd UV set), like the stadium looks in the game before the crowd and
// the grass are added. Same camera handling as KitPreview.

const LIGHT_MAP_INTENSITY = 1.6 // the baked light is stored dark; this brings it close to the game's look
type View = 'aerial' | 'pitch'
type Vec3 = [number, number, number]
const VIEWS: Record<View, { camera: Vec3; target: Vec3 }> = {
  aerial: { camera: [110, 80, 150], target: [0, 0, 0] },
  pitch: { camera: [-20, 8, -25], target: [10, 12, 60] },
}

const loader = new GLTFLoader()

/** The stadium's scene with its materials made unlit (diffuse texture × baked light). */
function useStadium(url: string, onProgress: (p: number) => void) {
  const [state, setState] = useState<{ url: string; scene?: THREE.Group; error?: string }>()
  const progress = useRef(onProgress)
  useEffect(() => {
    progress.current = onProgress
  })
  useEffect(() => {
    let alive = true
    loader.load(
      url,
      (gltf) => {
        gltf.scene.traverse((o) => {
          const mesh = o as THREE.Mesh
          if (!mesh.isMesh) return
          const m = mesh.material as THREE.MeshStandardMaterial
          const basic = new THREE.MeshBasicMaterial({ map: m.map, color: m.color, side: THREE.DoubleSide, alphaTest: m.alphaTest })
          if (m.aoMap) {
            basic.lightMap = m.aoMap
            basic.lightMap.channel = 1
            basic.lightMapIntensity = LIGHT_MAP_INTENSITY
          }
          mesh.material = basic
          m.dispose()
        })
        if (alive) setState({ url, scene: gltf.scene })
      },
      (e) => e.total && progress.current(e.loaded / e.total),
      (e) => alive && setState({ url, error: String((e as Error)?.message ?? e) }),
    )
    return () => {
      alive = false
    }
  }, [url])
  useEffect(
    () => () => {
      state?.scene?.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (!mesh.isMesh) return
        mesh.geometry.dispose()
        const m = mesh.material as THREE.MeshBasicMaterial
        m.map?.dispose()
        m.lightMap?.dispose()
        m.dispose()
      })
    },
    [state],
  )
  return state?.url === url ? state : undefined
}

/** Smoothly moves the camera to a view; a user drag cancels it. */
function CameraRig({ goal }: { goal: { camera: THREE.Vector3; target: THREE.Vector3 } | null }) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null
  const active = useRef(goal)
  useEffect(() => {
    active.current = goal
  }, [goal])
  useEffect(() => {
    if (!controls) return
    const stop = () => (active.current = null)
    controls.addEventListener('start', stop)
    return () => controls.removeEventListener('start', stop)
  }, [controls])
  useFrame((_, delta) => {
    const g = active.current
    if (!g || !controls) return
    const t = 1 - Math.exp(-delta * 6)
    camera.position.lerp(g.camera, t)
    controls.target.lerp(g.target, t)
    controls.update()
    if (camera.position.distanceTo(g.camera) < 0.05 && controls.target.distanceTo(g.target) < 0.05) active.current = null
  })
  return null
}

const goalOf = (v: View) => ({ camera: new THREE.Vector3(...VIEWS[v].camera), target: new THREE.Vector3(...VIEWS[v].target) })

export default function StadiumPreview({ id, times }: { id: number; times: number[] }) {
  const { t } = useI18n()
  const token = useToken()
  const [tod, setTod] = useState(times.includes(1) ? 1 : (times[0] ?? 1))
  const [view, setView] = useState<View>('aerial')
  const [goal, setGoal] = useState<ReturnType<typeof goalOf> | null>(null)
  const [progress, setProgress] = useState(0)
  const url = `/api/preview/stadium/${id}.glb?tod=${tod}&v=${token}`
  const loaded = useStadium(url, setProgress)
  const choose = (v: View) => {
    setView(v)
    setGoal(goalOf(v))
  }
  const button = (active: boolean) => cn('rounded px-2 py-0.5', active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')
  return (
    <div className="relative size-full">
      <Canvas flat camera={{ position: VIEWS.aerial.camera, fov: 50, near: 0.5, far: 2000 }} dpr={[1, 2]}>
        <color attach="background" args={[tod === 3 ? '#0d1424' : '#9cc4e4']} />
        {loaded?.scene && <primitive object={loaded.scene} />}
        <OrbitControls makeDefault target={VIEWS.aerial.target} minDistance={5} maxDistance={600} />
        <CameraRig goal={goal} />
      </Canvas>
      <div className="absolute top-2 right-2 flex gap-2 text-xs">
        {times.length > 1 && (
          <div className="flex rounded-md border bg-background/80 p-0.5 backdrop-blur">
            {times.map((v) => (
              <button key={v} type="button" onClick={() => setTod(v)} className={button(tod === v)}>
                {v === 3 ? t('stadium3d.night') : t('stadium3d.day')}
              </button>
            ))}
          </div>
        )}
        <div className="flex rounded-md border bg-background/80 p-0.5 backdrop-blur">
          {(['aerial', 'pitch'] as const).map((v) => (
            <button key={v} type="button" onClick={() => choose(v)} className={button(view === v)}>
              {v === 'aerial' ? t('stadium3d.aerial') : t('stadium3d.pitch')}
            </button>
          ))}
        </div>
      </div>
      {!loaded && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-6 animate-spin" />
          {progress > 0 ? t('stadium3d.downloading', { percent: Math.round(progress * 100) }) : t('stadium3d.building')}
        </div>
      )}
      {loaded?.error && <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-destructive">{t('stadium3d.failed', { error: loaded.error })}</div>}
    </div>
  )
}
