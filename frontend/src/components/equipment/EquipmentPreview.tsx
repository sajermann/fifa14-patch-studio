import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { EquipmentKind } from "@/api/types";
import { MODEL_REVISION } from "@/components/equipment/equipment";
import { useI18n } from "@/i18n";

// 3D preview of a boot, glove or ball (the Street Studio's BootPreview / GlovePreview / BallPreview): the item's own
// model with its color texture, from the project's files (as saved) or the game's. The model keeps its place on the
// player (centimeters made meters), so the cameras are the Street Studio's: the pair of boots, the right glove, the
// ball whole. Left drag turns, right drag moves, the wheel zooms.

type Loaded = {
  parts: THREE.BufferGeometry[];
  map: THREE.Texture;
  target: [number, number, number];
};

/** The Street Studio's views: camera offset from what it looks at (meters), and the zoom limits. */
const VIEWS: Record<
  EquipmentKind,
  { offset: [number, number, number]; near: number; min: number; max: number }
> = {
  boot: { offset: [0.62, 0.22, 0.58], near: 0.02, min: 0.2, max: 2.5 },
  glove: { offset: [0.32, 0.28, 0.42], near: 0.02, min: 0.15, max: 2.5 },
  ball: { offset: [0.25, 0.12, 0.42], near: 0.01, min: 0.18, max: 1.5 },
};

function useItem(kind: EquipmentKind, code: number, version: number) {
  const [state, setState] = useState<{
    key: string;
    loaded?: Loaded;
    failed?: boolean;
  }>({ key: "" });
  const key = `${kind}/${code}?v=${version}`;
  useEffect(() => {
    let alive = true;
    const base = `/api/equipment/${kind}/${code}`;
    Promise.all([
      new GLTFLoader().loadAsync(
        `${base}/preview.glb?v=${version}&r=${MODEL_REVISION}`,
      ),
      new THREE.TextureLoader().loadAsync(`${base}/preview.png?v=${version}`),
    ])
      .then(([gltf, map]) => {
        map.flipY = false;
        map.colorSpace = THREE.SRGBColorSpace;
        const parts: THREE.BufferGeometry[] = [];
        gltf.scene.traverse((o) => {
          if ((o as THREE.Mesh).isMesh) parts.push((o as THREE.Mesh).geometry);
        });
        // the game's centimeters as meters; looked at: the pair of boots, the right glove (x > 0), the ball
        const box = new THREE.Box3();
        const v = new THREE.Vector3();
        parts.forEach((g) => {
          g.scale(0.01, 0.01, 0.01);
          if (!g.getAttribute("normal")) g.computeVertexNormals();
          const pos = g.getAttribute("position");
          for (let i = 0; i < pos.count; i++) {
            v.fromBufferAttribute(pos, i);
            if (kind !== "glove" || v.x > 0) box.expandByPoint(v);
          }
        });
        const target = (
          box.isEmpty() ? [0, 0, 0] : box.getCenter(v).toArray()
        ) as [number, number, number];
        if (alive) setState({ key, loaded: { parts, map, target } });
      })
      .catch(() => alive && setState({ key, failed: true }));
    return () => {
      alive = false;
    };
  }, [kind, code, version, key]);
  return state.key === key ? state : { key };
}

export function EquipmentPreview({
  kind,
  code,
  version,
  empty,
}: {
  kind: EquipmentKind;
  code: number;
  version: number;
  empty?: string;
}) {
  const { t } = useI18n();
  const item = useItem(kind, code, version);
  if (item.failed || empty)
    return (
      <div className="flex size-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        {empty ?? t("equipment.previewFailed")}
      </div>
    );
  if (!item.loaded)
    return (
      <div className="flex size-full items-center justify-center text-muted-foreground">
        <LoaderCircle className="size-6 animate-spin" />
      </div>
    );
  const { target } = item.loaded;
  const view = VIEWS[kind];
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      camera={{
        position: [
          target[0] + view.offset[0],
          target[1] + view.offset[1],
          target[2] + view.offset[2],
        ],
        fov: 30,
        near: view.near,
        far: 10,
      }}
      title={t("equipment.previewControls")}
      onCreated={({ camera }) => camera.lookAt(...target)}
    >
      <hemisphereLight args={["#ffffff", "#6a6058", 1.6]} />
      <directionalLight
        position={[target[0] + 0.6, target[1] + 2.4, target[2] + 1.6]}
        intensity={2.0}
      />
      <directionalLight
        position={[target[0] - 0.9, target[1] + 1.8, target[2] + 0.8]}
        intensity={0.8}
      />
      <directionalLight
        position={[target[0], target[1] + 2, target[2] - 1.5]}
        intensity={0.8}
      />
      {item.loaded.parts.map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial
            map={item.loaded!.map}
            roughness={0.55}
            metalness={0}
            side={THREE.DoubleSide}
          />
        </mesh>
      ))}
      <OrbitControls
        makeDefault
        target={target}
        minDistance={view.min}
        maxDistance={view.max}
      />
    </Canvas>
  );
}
