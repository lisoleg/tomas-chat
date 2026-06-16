import React, { useRef, useEffect, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

// ── Types ──────────────────────────────────────────────

interface SpatialVertex {
  id: string;
  concept: string;
  position: [number, number, number];
  iValue: number;       // ℐ 值
  dikwpLayer: 'Data' | 'Info' | 'Knowledge' | 'Wisdom' | 'Purpose';
  isDead: boolean;      // 死零标记
  evidenceFlag: string;
}

interface SpatialEdge {
  id: string;
  source: string;
  target: string;
  relationType: string;
  asym: number;
}

interface SceneData {
  vertices: SpatialVertex[];
  edges: SpatialEdge[];
  deadZeroCount: number;
  totalObjects: number;
}

// ── DIKWP Color Map ────────────────────────────────────

const DIKWP_COLORS: Record<string, number> = {
  Data: 0xf59e0b,       // amber
  Info: 0x06b6d4,       // cyan
  Knowledge: 0x8b5cf6,  // violet
  Wisdom: 0xec4899,     // pink
  Purpose: 0x10b981,    // emerald
};

const DEAD_ZERO_COLOR = 0x6b7280; // gray

// ── Mock Scene Generator ───────────────────────────────

function generateMockScene(): SceneData {
  const vertices: SpatialVertex[] = [];
  const edges: SpatialEdge[] = [];

  // Room layout objects
  const objects = [
    { concept: '地板', pos: [0, -2, 0], dikwp: 'Data' as const, iVal: 0.9 },
    { concept: '墙壁-北', pos: [0, 0, -3], dikwp: 'Data' as const, iVal: 0.85 },
    { concept: '墙壁-南', pos: [0, 0, 3], dikwp: 'Data' as const, iVal: 0.85 },
    { concept: '墙壁-东', pos: [3, 0, 0], dikwp: 'Data' as const, iVal: 0.85 },
    { concept: '墙壁-西', pos: [-3, 0, 0], dikwp: 'Data' as const, iVal: 0.85 },
    { concept: '天花板', pos: [0, 2, 0], dikwp: 'Data' as const, iVal: 0.8 },
    { concept: '沙发', pos: [0, -1, 2], dikwp: 'Knowledge' as const, iVal: 0.65 },
    { concept: '茶几', pos: [0, -1.2, 0.5], dikwp: 'Knowledge' as const, iVal: 0.55 },
    { concept: '电视', pos: [2.5, -0.5, -2.8], dikwp: 'Knowledge' as const, iVal: 0.6 },
    { concept: '台灯', pos: [-1.5, -0.8, 1.5], dikwp: 'Info' as const, iVal: 0.4 },
    { concept: '书架', pos: [-2.8, 0.3, -1], dikwp: 'Wisdom' as const, iVal: 0.7 },
    { concept: '花瓶', pos: [0, -1.1, 0.5], dikwp: 'Info' as const, iVal: 0.2, dead: true },
    { concept: '地毯', pos: [0, -1.95, 0.5], dikwp: 'Data' as const, iVal: 0.35 },
    { concept: '窗户', pos: [-3, 0.3, -1.5], dikwp: 'Data' as const, iVal: 0.5 },
    { concept: '门', pos: [3, -0.3, -1.5], dikwp: 'Data' as const, iVal: 0.55 },
    { concept: '画框', pos: [-2.5, 0.5, -2.9], dikwp: 'Purpose' as const, iVal: 0.3 },
    { concept: '吊灯', pos: [0, 1.8, 0], dikwp: 'Knowledge' as const, iVal: 0.45 },
    { concept: '植物', pos: [1.5, -1.2, -2], dikwp: 'Info' as const, iVal: 0.38 },
    { concept: '遥控器', pos: [0.3, -1.15, 0.3], dikwp: 'Info' as const, iVal: 0.15 },
    // Floating (dead-zero) objects
    { concept: '浮空球', pos: [0, 0.8, 1], dikwp: 'Purpose' as const, iVal: 0.05, dead: true },
  ];

  vertices.push(...objects.map((o, i) => ({
    id: `v${i}`,
    concept: o.concept,
    position: o.pos as [number, number, number],
    iValue: o.iVal,
    dikwpLayer: o.dikwp,
    isDead: o.dead || false,
    evidenceFlag: o.dead ? 'UNGROUNDED' : 'EMPIRICAL',
  })));

  // Edges: spatial relations
  const relations: [number, number, string, number][] = [
    [6, 7, 'supported_by', 0.1],    // 沙发 supported_by 地板
    [7, 0, 'supported_by', 0.05],   // 茶几 supported_by 地板
    [8, 1, 'attached_to', 0.08],    // 电视 attached_to 墙壁-北
    [13, 1, 'contains', 0.12],       // 墙壁-北 contains 窗户 (window in wall)
    [14, 2, 'contains', 0.12],       // 墙壁-南 contains 门
    [15, 1, 'attached_to', 0.05],   // 画框 attached_to 墙壁-北
    [10, 2, 'near', 0.15],           // 书架 near 墙壁-南
    [10, 7, 'above', 0.2],           // 花瓶 above 茶几 (sits on it)
    [9, 13, 'near', 0.18],           // 台灯 near 窗户
    [16, 0, 'adjacent', 0.05],       // 吊灯 adjacent 天花板
  ];

  edges.push(...relations.map(([s, t, r, a], i) => ({
    id: `e${i}`,
    source: `v${s}`,
    target: `v${t}`,
    relationType: r,
    asym: a,
  })));

  const deadZeroCount = vertices.filter(v => v.isDead).length;
  return { vertices, edges, deadZeroCount, totalObjects: vertices.length };
}

// ── Component ──────────────────────────────────────────

export default function WorldModelViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const spheresRef = useRef<Map<string, THREE.Mesh>>(new Map());

  const [sceneData, setSceneData] = useState<SceneData | null>(null);
  const [hoveredVertex, setHoveredVertex] = useState<SpatialVertex | null>(null);
  const [showDeadZero, setShowDeadZero] = useState(true);
  const [showEdges, setShowEdges] = useState(true);
  const [showGrid, setShowGrid] = useState(true);

  // Generate mock scene
  useEffect(() => {
    setSceneData(generateMockScene());
  }, []);

  // Initialize Three.js
  useEffect(() => {
    if (!mountRef.current) return;

    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1b2e);
    scene.fog = new THREE.Fog(0x1a1b2e, 8, 20);
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.5, 50);
    camera.position.set(6, 4, 6);
    camera.lookAt(0, -0.5, 0);
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    mountRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, -0.5, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 3;
    controls.maxDistance = 15;
    controls.maxPolarAngle = Math.PI * 0.7;
    controls.update();
    controlsRef.current = controls;

    // Grid
    const gridHelper = new THREE.GridHelper(10, 20, 0x444466, 0x222244);
    gridHelper.position.y = -2;
    scene.add(gridHelper);
    gridHelper.name = 'grid';

    // Lights
    const ambientLight = new THREE.AmbientLight(0x404060, 2);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1.5);
    directionalLight.position.set(5, 8, 3);
    directionalLight.castShadow = true;
    scene.add(directionalLight);

    // Raycaster for hover
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onMouseMove = (e: MouseEvent) => {
      const rect = mountRef.current!.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects([...spheresRef.current.values()]);

      if (intersects.length > 0) {
        const obj = intersects[0].object as THREE.Mesh;
        const vid = obj.userData.vertexId;
        const vertex = sceneData?.vertices.find(v => v.id === vid);
        setHoveredVertex(vertex || null);
      } else {
        setHoveredVertex(null);
      }
    };

    mountRef.current.addEventListener('mousemove', onMouseMove);

    // Animation loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Resize
    const onResize = () => {
      if (!mountRef.current || !camera || !renderer) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
      mountRef.current?.removeEventListener('mousemove', onMouseMove);
      controls.dispose();
      renderer.dispose();
      mountRef.current?.removeChild(renderer.domElement);
    };
  }, []);

  // Update scene objects when data or toggles change
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !sceneData) return;

    // Clear old spheres
    spheresRef.current.forEach(mesh => scene.remove(mesh));
    spheresRef.current.clear();

    // Remove old edges
    scene.children
      .filter(c => c.name === 'edge')
      .forEach(c => scene.remove(c));

    // Add vertices
    sceneData.vertices.forEach(v => {
      if (!showDeadZero && v.isDead) return;

      const color = v.isDead ? DEAD_ZERO_COLOR : (DIKWP_COLORS[v.dikwpLayer] || 0x888888);
      const size = v.isDead ? 0.12 : Math.max(0.1, v.iValue * 0.35);

      const geo = new THREE.SphereGeometry(size, 16, 16);
      const mat = new THREE.MeshPhongMaterial({
        color,
        emissive: color,
        emissiveIntensity: v.isDead ? 0.05 : 0.3,
        specular: 0x222222,
        shininess: 20,
        transparent: v.isDead,
        opacity: v.isDead ? 0.35 : 1,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(...v.position);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData = { vertexId: v.id, concept: v.concept };
      mesh.name = 'vertex';
      scene.add(mesh);
      spheresRef.current.set(v.id, mesh);
    });

    // Add edges
    if (showEdges) {
      sceneData.edges.forEach(e => {
        const srcMesh = spheresRef.current.get(e.source);
        const tgtMesh = spheresRef.current.get(e.target);
        if (!srcMesh || !tgtMesh) return;

        const srcVertex = sceneData.vertices.find(v => v.id === e.source);
        const tgtVertex = sceneData.vertices.find(v => v.id === e.target);
        if (srcVertex?.isDead || tgtVertex?.isDead) {
          if (!showDeadZero) return;
        }

        const points = [srcMesh.position, tgtMesh.position];
        const geo = new THREE.BufferGeometry().setFromPoints(points);
        const alpha = Math.max(0.1, 1 - e.asym * 3);
        const mat = new THREE.LineBasicMaterial({
          color: 0x4a5568,
          transparent: true,
          opacity: alpha,
        });
        const line = new THREE.Line(geo, mat);
        line.name = 'edge';
        scene.add(line);
      });
    }

    // Toggle grid
    const grid = scene.children.find(c => c.name === 'grid');
    if (grid) grid.visible = showGrid;
  }, [sceneData, showDeadZero, showEdges, showGrid]);

  const dikwpLegend = [
    { layer: 'Data', color: '#f59e0b' },
    { layer: 'Info', color: '#06b6d4' },
    { layer: 'Knowledge', color: '#8b5cf6' },
    { layer: 'Wisdom', color: '#ec4899' },
    { layer: 'Purpose', color: '#10b981' },
  ];

  return (
    <div ref={containerRef} className="flex-1 flex flex-col">
      {/* Header */}
      <div className="px-4 md:px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-textPrimary">HY World 2.0 — 世界模型</h1>
        <p className="text-sm text-textSecondary mt-1">
          腾讯混元 3D 场景 — 顶点颜色=DIKWP 层，大小=ℐ 值，灰色透明=死零
        </p>
      </div>

      {/* Controls */}
      <div className="px-4 md:px-6 pb-2 flex flex-wrap gap-3 items-center">
        {sceneData && (
          <span className="text-xs text-textSecondary">
            顶点: <span className="text-textPrimary">{sceneData.totalObjects - sceneData.deadZeroCount}</span>
            <span className="mx-1">+</span>
            <span className={`${showDeadZero ? 'text-red-400' : 'text-textSecondary'}`}>
              {sceneData.deadZeroCount} 死零
            </span>
          </span>
        )}
        <label className="flex items-center gap-1.5 text-xs text-textSecondary cursor-pointer">
          <input
            type="checkbox"
            checked={showDeadZero}
            onChange={e => setShowDeadZero(e.target.checked)}
            className="accent-accent w-3 h-3"
          />
          显示死零
        </label>
        <label className="flex items-center gap-1.5 text-xs text-textSecondary cursor-pointer">
          <input
            type="checkbox"
            checked={showEdges}
            onChange={e => setShowEdges(e.target.checked)}
            className="accent-accent w-3 h-3"
          />
          显示边
        </label>
        <label className="flex items-center gap-1.5 text-xs text-textSecondary cursor-pointer">
          <input
            type="checkbox"
            checked={showGrid}
            onChange={e => setShowGrid(e.target.checked)}
            className="accent-accent w-3 h-3"
          />
          网格
        </label>
      </div>

      {/* 3D Viewport */}
      <div className="flex-1 mx-4 md:mx-6 mb-4 rounded-xl overflow-hidden border border-borderSubtle/30 bg-[#1a1b2e] relative min-h-[400px]">
        <div ref={mountRef} className="w-full h-full absolute inset-0" />

        {/* Hover tooltip */}
        {hoveredVertex && (
          <div className="absolute top-3 left-3 bg-chatBgAlt/95 backdrop-blur-sm border border-borderSubtle/50 rounded-lg px-3 py-2 pointer-events-none z-10">
            <p className="text-xs font-medium text-textPrimary">{hoveredVertex.concept}</p>
            <div className="flex gap-3 mt-1">
              <span className="text-[10px] text-textSecondary">
                ℐ: <span className={hoveredVertex.isDead ? 'text-red-400' : 'text-accent'}>
                  {hoveredVertex.iValue.toFixed(2)}
                </span>
              </span>
              <span className="text-[10px] text-textSecondary">
                {hoveredVertex.dikwpLayer}
              </span>
              {hoveredVertex.isDead && (
                <span className="text-[10px] text-red-400 font-medium">⚡ 死零</span>
              )}
            </div>
            <p className="text-[10px] text-textSecondary mt-0.5">
              {hoveredVertex.evidenceFlag}
            </p>
          </div>
        )}

        {/* DIKWP Legend */}
        <div className="absolute bottom-3 right-3 bg-chatBgAlt/90 backdrop-blur-sm border border-borderSubtle/50 rounded-lg px-3 py-2 z-10">
          <p className="text-[10px] text-textSecondary mb-1.5">DIKWP 层</p>
          <div className="flex gap-2">
            {dikwpLegend.map(l => (
              <div key={l.layer} className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: l.color }} />
                <span className="text-[10px] text-textSecondary">{l.layer[0]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Inspector Panel */}
      {sceneData && (
        <div className="px-4 md:px-6 pb-4">
          <div className="bg-chatBgAlt rounded-xl border border-borderSubtle/30 p-3">
            <h3 className="text-xs font-medium text-textSecondary mb-2">场景对象清单</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
              {sceneData.vertices.map(v => (
                <div
                  key={v.id}
                  className={`text-[11px] px-2 py-1 rounded flex items-center gap-1.5 ${
                    v.isDead ? 'bg-red-900/20 text-red-400' : 'bg-chatBg text-textPrimary'
                  }`}
                  onMouseEnter={() => {
                    const mesh = spheresRef.current.get(v.id);
                    if (mesh) {
                      const orig = (mesh.material as THREE.MeshPhongMaterial).emissiveIntensity;
                      (mesh.material as THREE.MeshPhongMaterial).emissiveIntensity = 0.8;
                      setTimeout(() => {
                        (mesh.material as THREE.MeshPhongMaterial).emissiveIntensity = orig;
                      }, 300);
                    }
                  }}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: v.isDead ? '#6b7280' : DIKWP_COLORS[v.dikwpLayer] ? `#${DIKWP_COLORS[v.dikwpLayer].toString(16).padStart(6, '0')}` : '#888' }}
                  />
                  <span className="truncate">{v.concept}</span>
                  {v.isDead && <span className="text-[9px] ml-auto">死零</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
