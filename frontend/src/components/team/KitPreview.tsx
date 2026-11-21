import { OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { PreviewLook } from '@/api/types'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useToken } from '@/state/queries'

// Live 3D preview of a kit: a generic player of the game (head, face, hair, skin, boots: always the same) wearing the
// kit's jersey and shorts textures (the socks are mapped on the shorts texture), with the crest, name and numbers the
// game draws over them (a transparent layer from the backend), shaded like the game does with the kit occlusion maps.
// Each part loads on its own and keeps showing the previous version until the new one is ready.

/** Shown until the wearer's look arrives (and when the squad is empty). */
export const MODEL_LOOK: PreviewLook = { real: false, head: 1, hair: 1, hair_color: '#1f160e', eyes: 1, face: '0_0_0_0_0_4', skin: 4, sleeve: 0, socks: 0, shoe: 0, glove: 1, scale: 1 }

/** What the player wears: the kit's textures (null = the kit has none, shown grey), the crest/name/numbers layers,
 * its collar mesh and whether it is the goalkeeper's (gloves). */
export interface PreviewKit {
  jersey: string | null
  shorts: string | null
  jerseyPrint: string | null
  shortsPrint: string | null
  collar: number
  goalkeeper: boolean
}

const HAIR_TINT_GAIN = 1.8 // the game's hair_cm is a mid grey brightened by its shader
export type View = 'face' | 'body'
type Vec3 = [number, number, number]
const VIEWS: Record<View, { camera: Vec3; target: Vec3 }> = {
  face: { camera: [0, 1.62, 1.25], target: [0, 1.58, 0] },
  body: { camera: [0, 1.0, 4.1], target: [0, 1.0, 0] },
}

// ------------------------------------------------------------------ loading (cached, no Suspense)

// The browser keeps the preview's files for an hour (Cache-Control) and a page reload does not refetch them: bump
// when what an existing URL serves changes, or a stale copy breaks the preview (2: pack faces in a newer format
// come converted into FIFA 14's meshes).
const ASSETS_VERSION = '2'
const versioned = (url: string) => `${url}${url.includes('?') ? '&' : '?'}v=${ASSETS_VERSION}`

const cache = new Map<string, Promise<unknown>>()
const gltfLoader = new GLTFLoader()
const textureLoader = new THREE.TextureLoader()
let pending = 0
const pendingListeners = new Set<() => void>()
const setPending = (delta: number) => {
  pending += delta
  pendingListeners.forEach((l) => l())
}
const subscribePending = (listener: () => void) => {
  pendingListeners.add(listener)
  return () => pendingListeners.delete(listener)
}

function cached<T>(url: string, load: () => Promise<T>): Promise<T> {
  let p = cache.get(url) as Promise<T> | undefined
  if (!p) {
    p = load()
    setPending(1)
    p.finally(() => setPending(-1)).catch(() => undefined)
    p.catch(() => cache.delete(url)) // allow a retry after a failure
    cache.set(url, p)
  }
  return p
}

function useLoading(delayMs = 200) {
  const busy = useSyncExternalStore(subscribePending, () => pending > 0)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setShown(busy), busy ? delayMs : 0)
    return () => clearTimeout(timer)
  }, [busy, delayMs])
  return busy && shown
}

/** Geometries of a GLB by node name. */
function loadMeshes(url: string) {
  return cached(url, async () => {
    const gltf = await gltfLoader.loadAsync(versioned(url))
    const out: Record<string, THREE.BufferGeometry[]> = {}
    gltf.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      const geometry = mesh.geometry
      if (!geometry.attributes.uv1 && geometry.attributes.uv) geometry.setAttribute('uv1', geometry.attributes.uv)
      out[o.name] = [...(out[o.name] ?? []), geometry]
    })
    return out
  })
}

/** color = false for data textures (opacity, shading); channel = UV set the texture is sampled with. */
function loadTexture(url: string, color = true, channel = 0, repeat = false) {
  return cached(`${url}|${channel}`, async () => {
    const texture = await textureLoader.loadAsync(versioned(url))
    if (repeat) texture.wrapS = texture.wrapT = THREE.RepeatWrapping
    texture.flipY = false // RX3 UVs have their origin at the top left, like glTF
    texture.channel = channel
    texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace
    texture.anisotropy = 4
    return texture
  })
}

let missing: THREE.Texture | undefined

/** The blue and green checkers the game draws where a texture is missing (a face without its eyes texture). */
function missingTexture() {
  if (!missing) {
    const n = 8
    const data = new Uint8Array(n * n * 4)
    for (let i = 0; i < n * n; i++) {
      const [r, g, b] = ((i % n) + Math.floor(i / n)) % 2 ? [40, 90, 220] : [40, 200, 70]
      data.set([r, g, b, 255], i * 4)
    }
    missing = new THREE.DataTexture(data, n, n)
    missing.wrapS = missing.wrapT = THREE.RepeatWrapping
    missing.repeat.set(0.5, 0.5)
    missing.magFilter = THREE.NearestFilter
    missing.colorSpace = THREE.SRGBColorSpace
    missing.needsUpdate = true
  }
  return missing
}

/** Value of load() for key; keeps returning the previous value while a new key loads. */
function useLoaded<T>(key: string | null, load: () => Promise<T>): T | undefined {
  const [state, setState] = useState<{ key: string; value: T }>()
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })
  useEffect(() => {
    if (key === null) return
    let alive = true
    loadRef.current().then(
      (value) => alive && setState({ key, value }),
      () => undefined, // missing file: keep what is on screen
    )
    return () => {
      alive = false
    }
  }, [key])
  return key === null ? undefined : state?.value
}

// ------------------------------------------------------------------ parts

function useAssetUrl() {
  const token = useToken()
  return (path: string) => `${path}${path.includes('?') ? '&' : '?'}v=${token}`
}

const meshUrl = (part: string, code: number, collar = 0, real = false) => `/api/preview/mesh/${part}/${code}.glb${collar ? `?collar=${collar}` : real ? '?real=1' : ''}`
const textureUrl = (name: string, code: number, real = false) => `/api/preview/texture/${name}/${code}.png${real ? '?real=1' : ''}`

/** A face URL with the pack face (or the one kept in the project) the look carries. */
const withFace = (path: string, look: PreviewLook) => (look.real && look.query ? `${path}${path.includes('?') ? '&' : '?'}${look.query}` : path)

function Head({ look }: { look: PreviewLook }) {
  const url = useAssetUrl()
  const [glb, face] = [meshUrl('head', look.head, 0, look.real), `/api/preview/face/${look.face}.png`].map((p) => url(withFace(p, look)))
  // a face without its eyes texture: checkered eyes, like the game shows a missing texture (nothing is filled in)
  const eyes = look.eyes === null ? null : url(withFace(textureUrl('eyes', look.eyes, look.real), look))
  const loaded = useLoaded([glb, face, eyes].join('|'), () =>
    Promise.all([loadMeshes(glb), loadTexture(face), eyes === null ? Promise.resolve(missingTexture()) : loadTexture(eyes, true, 0, true)]),
  )
  if (!loaded) return null
  const [meshes, faceMap, eyesMap] = loaded
  return (
    <group>
      {meshes.head?.map((g, i) => (
        <mesh key={`head${i}`} geometry={g}>
          <meshStandardMaterial map={faceMap} roughness={0.75} metalness={0} />
        </mesh>
      ))}
      {meshes.eyes?.map((g, i) => (
        <mesh key={`eyes${i}`} geometry={g}>
          <meshStandardMaterial map={eyesMap} roughness={0.25} metalness={0} />
        </mesh>
      ))}
    </group>
  )
}

function Hair({ look }: { look: PreviewLook }) {
  const url = useAssetUrl()
  const { hair, real } = look
  const urls = [meshUrl('hair', hair, 0, real), textureUrl('hair', hair, real), textureUrl('hair-cap', hair, real), textureUrl('hair-strands', hair, real)].map((p) => url(withFace(p, look)))
  // hair_cm uses the first UV set; the opacity (hair_coeff) the second one
  const loaded = useLoaded(hair ? urls.join('|') : null, () =>
    Promise.all([loadMeshes(urls[0]), loadTexture(urls[1]), loadTexture(urls[2], false, 1), loadTexture(urls[3], false, 1)]),
  )
  const color = useMemo(() => new THREE.Color(look.hair_color).multiplyScalar(HAIR_TINT_GAIN), [look.hair_color])
  if (!loaded) return null // also bald (hair 0)
  const [meshes, hairMap, cap, strands] = loaded
  return (
    <group>
      {(
        [
          ['cap', cap],
          ['strands', strands],
        ] as const
      ).flatMap(([part, alpha]) =>
        (meshes[part] ?? []).map((g, i) => (
          <mesh key={`${part}${i}`} geometry={g} renderOrder={part === 'cap' ? 1 : 2}>
            <meshLambertMaterial map={hairMap} alphaMap={alpha} color={color} alphaToCoverage alphaTest={0.05} side={part === 'cap' ? THREE.FrontSide : THREE.DoubleSide} />
          </mesh>
        )),
      )}
    </group>
  )
}

/** A part with a plain texture (skin, boots, gloves). */
function Part({ part, code, texture, roughness }: { part: string; code: number; texture: string; roughness: number }) {
  const url = useAssetUrl()
  const [glb, map] = [url(meshUrl(part, code)), url(texture)]
  const loaded = useLoaded(`${glb}|${map}`, () => Promise.all([loadMeshes(glb), loadTexture(map)]))
  if (!loaded) return null
  return (
    <group>
      {(loaded[0][part] ?? []).map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial map={loaded[1]} roughness={roughness} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

const GREY = new THREE.DataTexture(new Uint8Array([170, 170, 170, 255]), 1, 1)
GREY.needsUpdate = true
const CLEAR = new THREE.DataTexture(new Uint8Array(4), 1, 1)
CLEAR.needsUpdate = true

/** Kit material: the kit texture with the crest/name/numbers layer over it, multiplied by the game's occlusion map
 * of the jersey or the shorts (all with the same UVs). */
function useKitMaterial(map: THREE.Texture | undefined, shade: THREE.Texture | undefined, print: THREE.Texture | undefined) {
  const uniforms = useMemo(() => ({ uShade: { value: GREY as THREE.Texture }, uPrint: { value: CLEAR as THREE.Texture } }), [])
  const material = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({ map: map ?? GREY, roughness: 0.85, metalness: 0, side: THREE.DoubleSide })
    m.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms)
      shader.fragmentShader = shader.fragmentShader
        .replace('void main() {', 'uniform sampler2D uShade;\nuniform sampler2D uPrint;\nvoid main() {')
        .replace(
          '#include <map_fragment>',
          '#include <map_fragment>\n' +
            'vec4 printTexel = texture2D( uPrint, vMapUv );\n' +
            'diffuseColor.rgb = mix( diffuseColor.rgb, printTexel.rgb, printTexel.a );\n' +
            'diffuseColor.rgb *= texture2D( uShade, vMapUv ).r;',
        )
    }
    return m
  }, [map, uniforms])
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => {
    uniforms.uShade.value = shade ?? GREY
    uniforms.uPrint.value = print ?? CLEAR
  })
  return material
}

/** A part wearing the kit: jersey (jersey texture) or shorts/socks (shorts texture). */
function KitPart({
  part,
  code,
  collar = 0,
  texture,
  print,
  shade,
}: {
  part: 'jersey' | 'shorts' | 'socks'
  code: number
  collar?: number
  texture: string | null
  print: string | null
  shade: string
}) {
  const url = useAssetUrl()
  const glb = url(meshUrl(part, code, collar))
  const shadeUrl = url(shade)
  const loaded = useLoaded(`${glb}|${texture}|${print}|${shadeUrl}`, () =>
    Promise.all([
      loadMeshes(glb),
      texture ? loadTexture(texture) : Promise.resolve(undefined),
      loadTexture(shadeUrl, false),
      print ? loadTexture(print) : Promise.resolve(undefined),
    ]),
  )
  const material = useKitMaterial(loaded?.[1], loaded?.[2], loaded?.[3])
  if (!loaded) return null
  return (
    <group>
      {(loaded[0][part] ?? []).map((g, i) => (
        <mesh key={i} geometry={g} material={material} />
      ))}
    </group>
  )
}

function Player({ kit, look }: { kit: PreviewKit; look: PreviewLook }) {
  const sleeve = look.sleeve // 1 = long sleeves
  const skin = textureUrl('skin', look.skin)
  const shortsShade = textureUrl('shorts-shade', 0)
  return (
    <group scale={look.scale}>
      <Head look={look} />
      <Hair look={look} />
      <KitPart part="jersey" code={sleeve} collar={kit.collar} texture={kit.jersey} print={kit.jerseyPrint} shade={textureUrl('jersey-shade', sleeve)} />
      <Part part="arms" code={sleeve} texture={skin} roughness={0.7} />
      <KitPart part="shorts" code={0} texture={kit.shorts} print={kit.shortsPrint} shade={shortsShade} />
      <KitPart part="socks" code={look.socks} texture={kit.shorts} print={null} shade={shortsShade} />
      <Part part="legs" code={look.socks} texture={skin} roughness={0.7} />
      <Part part="shoes" code={look.shoe} texture={textureUrl('shoe', look.shoe)} roughness={0.5} />
      {kit.goalkeeper && <Part part="gloves" code={look.glove} texture={textureUrl('glove', look.glove)} roughness={0.6} />}
    </group>
  )
}

// ------------------------------------------------------------------ camera and canvas

interface CameraGoal {
  camera: THREE.Vector3
  target: THREE.Vector3
}

/** A view's camera; the face view follows the head of a taller or shorter player. */
const presetGoal = (view: View, scale = 1): CameraGoal => {
  const s = view === 'face' ? scale : 1
  const [cx, cy, cz] = VIEWS[view].camera
  const [tx, ty, tz] = VIEWS[view].target
  return { camera: new THREE.Vector3(cx, cy * s, cz), target: new THREE.Vector3(tx, ty * s, tz) }
}

/** Smoothly moves the camera to a view; a user drag cancels it. */
function CameraRig({ goal }: { goal: CameraGoal | null }) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null
  const active = useRef<CameraGoal | null>(null)
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
    const t = 1 - Math.exp(-delta * 10)
    camera.position.lerp(g.camera, t)
    controls.target.lerp(g.target, t)
    controls.update()
    if (camera.position.distanceTo(g.camera) < 0.002 && controls.target.distanceTo(g.target) < 0.002) active.current = null
  })
  return null
}

function Scene({ kit, look, goal, initialView }: { kit: PreviewKit; look: PreviewLook; goal: CameraGoal | null; initialView: View }) {
  const [initialTarget] = useState(() => presetGoal(initialView, look.scale).target)
  return (
    <>
      {/* no tone mapping (Canvas flat): the game's textures already carry their shading */}
      <hemisphereLight args={['#ffffff', '#6a6058', 1.6]} />
      <directionalLight position={[0.6, 2.4, 1.6]} intensity={2.0} />
      <directionalLight position={[-0.9, 1.8, 0.8]} intensity={0.8} />
      <directionalLight position={[0, 2, -1.5]} intensity={0.8} />
      <Player kit={kit} look={look} />
      <OrbitControls makeDefault target={initialTarget} minDistance={0.4} maxDistance={6} />
      <CameraRig goal={goal} />
    </>
  )
}

/** `viewRequest`: a view the page asks for (a face option touched shows the face; seq makes the same view count
 * again), like the Street Studio's preview. */
export default function KitPreview({ kit, look, initialView = 'body', viewRequest }: { kit: PreviewKit; look?: PreviewLook; initialView?: View; viewRequest?: { view: View; seq: number } }) {
  const { t } = useI18n()
  const [view, setView] = useState<View>(initialView)
  const [goal, setGoal] = useState<CameraGoal | null>(null)
  const loading = useLoading()
  const shownLook = look ?? MODEL_LOOK
  const choose = (v: View) => {
    setView(v)
    setGoal(presetGoal(v, shownLook.scale))
  }
  const [lastRequest, setLastRequest] = useState(viewRequest?.seq)
  if (viewRequest && viewRequest.seq !== lastRequest) {
    setLastRequest(viewRequest.seq)
    setView(viewRequest.view)
    setGoal(presetGoal(viewRequest.view, shownLook.scale))
  }
  // the face view keeps the head framed when another player (taller or shorter) wears the kit
  const [lastScale, setLastScale] = useState(shownLook.scale)
  if (shownLook.scale !== lastScale) {
    setLastScale(shownLook.scale)
    if (view === 'face') setGoal(presetGoal('face', shownLook.scale))
  }
  return (
    <div className="relative size-full">
      <Canvas flat camera={{ position: presetGoal(initialView, shownLook.scale).camera.toArray(), fov: 30, near: 0.05, far: 20 }} dpr={[1, 2]}>
        <Scene kit={kit} look={shownLook} goal={goal} initialView={initialView} />
      </Canvas>
      <div className="absolute top-2 right-2 flex rounded-md border bg-background/80 p-0.5 text-xs backdrop-blur">
        {(['face', 'body'] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => choose(v)}
            className={cn('rounded px-2 py-0.5', view === v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
          >
            {v === 'face' ? t('preview.face') : t('preview.body')}
          </button>
        ))}
      </div>
      {loading && (
        <div className="pointer-events-none absolute top-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-md border bg-background/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur">
          <LoaderCircle className="size-3.5 animate-spin" /> {t('common.loading')}
        </div>
      )}
    </div>
  )
}
