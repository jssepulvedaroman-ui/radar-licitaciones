"""
Actualiza los datos del Radar de Licitaciones desde la API de Mercado Público.

Lo ejecuta GitHub Actions todos los días hábiles (ver .github/workflows/actualizar.yml),
pero también puedes correrlo en tu computador:

    set MP_TICKET=tu-ticket        (Windows)   |   export MP_TICKET=tu-ticket   (Mac/Linux)
    python scripts/actualizar.py

Variables opcionales:  DIAS=30 (días de histórico a revisar)   MAX_MINUTOS=240 (tope de ejecución)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
ARCHIVO_LICITACIONES = DATOS / "licitaciones.json"
ARCHIVO_ESTADO = DATOS / "estado.json"
URL_API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
ESTADOS = {5: "Publicada", 6: "Cerrada", 7: "Desierta", 8: "Adjudicada", 18: "Revocada", 19: "Suspendida"}
INICIO = time.time()


def normalizar(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto.lower()).strip()


def num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def rut_limpio(rut) -> str:
    return str(rut or "").replace(".", "").replace(" ", "").upper()


def minutos() -> float:
    return (time.time() - INICIO) / 60


class ErrorAPI(Exception):
    pass


class API:
    def __init__(self, ticket: str, pausa: float):
        self.ticket, self.pausa = ticket, pausa
        self.sesion = requests.Session()
        self.consultas, self._ultima = 0, 0.0

    def _get(self, params: dict) -> dict:
        params = {**params, "ticket": self.ticket}
        for intento in range(6):
            espera = self.pausa - (time.time() - self._ultima)
            if espera > 0:
                time.sleep(espera)
            self._ultima = time.time()
            try:
                r = self.sesion.get(URL_API, params=params, timeout=60)
                self.consultas += 1
                datos = r.json()
            except (requests.RequestException, ValueError) as e:
                print(f"  aviso: fallo de red ({e.__class__.__name__}), reintento {intento + 1}")
                time.sleep(5 * (intento + 1))
                continue
            if isinstance(datos, dict) and "Listado" in datos:
                return datos
            mensaje = str(datos.get("Mensaje", datos)) if isinstance(datos, dict) else str(datos)
            if "simult" in normalizar(mensaje) or str(datos.get("Codigo", "")) == "10500":
                time.sleep(5 * (intento + 1))
                continue
            raise ErrorAPI(mensaje)
        raise ErrorAPI("La API no respondió después de varios intentos.")

    def activas(self):
        return self._get({"estado": "activas"}).get("Listado") or []

    def por_fecha(self, dia: date, estado: str):
        return self._get({"fecha": dia.strftime("%d%m%Y"), "estado": estado}).get("Listado") or []

    def detalle(self, codigo: str):
        listado = self._get({"codigo": codigo}).get("Listado") or []
        return listado[0] if listado else None


def aplanar(d: dict, previo: dict | None, origen: str) -> dict:
    """Convierte el detalle de la API en un registro compacto para el panel."""
    comprador = d.get("Comprador") or {}
    fechas = d.get("Fechas") or {}
    adj = d.get("Adjudicacion") or {}
    estado_cod = int(num(d.get("CodigoEstado")) or 0)
    items, total, ganadores = [], 0.0, {}
    for it in (d.get("Items") or {}).get("Listado") or []:
        a = it.get("Adjudicacion") or {}
        unit, cant = num(a.get("MontoUnitario")), num(a.get("Cantidad"))
        if a and unit:
            t = (cant or 0) * unit
            total += t
            prov = a.get("NombreProveedor") or rut_limpio(a.get("RutProveedor"))
            ganadores[prov] = ganadores.get(prov, 0) + t
            items.append({"producto": it.get("NombreProducto"), "descripcion": (it.get("Descripcion") or "")[:300],
                          "unidad": it.get("UnidadMedida"), "cantidad": cant, "unitario": unit, "total": t,
                          "proveedor": prov, "rut": rut_limpio(a.get("RutProveedor"))})
    ahora = datetime.now().isoformat(timespec="seconds")
    origenes = set((previo or {}).get("origen", [])) | {origen}
    return {
        "codigo": d.get("CodigoExterno"),
        "nombre": d.get("Nombre"),
        "descripcion": (d.get("Descripcion") or "")[:600],
        "estado_cod": estado_cod,
        "estado": ESTADOS.get(estado_cod, d.get("Estado") or str(estado_cod)),
        "tipo": d.get("Tipo"),
        "organismo": comprador.get("NombreOrganismo"),
        "unidad": comprador.get("NombreUnidad"),
        "region": (comprador.get("RegionUnidad") or "").strip(),
        "comuna": (comprador.get("ComunaUnidad") or "").strip(),
        "publicacion": fechas.get("FechaPublicacion"),
        "cierre": fechas.get("FechaCierre") or d.get("FechaCierre"),
        "adjudicacion": fechas.get("FechaAdjudicacion") or adj.get("Fecha"),
        "visita": fechas.get("FechaVisitaTerreno"),
        "monto_estimado": num(d.get("MontoEstimado")) if int(num(d.get("VisibilidadMonto")) or 0) else None,
        "oferentes": int(num(adj.get("NumeroOferentes")) or 0) or None,
        "acta": adj.get("UrlActa"),
        "monto_adjudicado": total or None,
        "ganadores": sorted(ganadores, key=ganadores.get, reverse=True),
        "items": items,
        "origen": sorted(origenes),
        "primera_vez": (previo or {}).get("primera_vez", ahora),
        "actualizado": ahora,
    }


class Radar:
    def __init__(self, cfg: dict, api: API):
        self.cfg, self.api = cfg, api
        self.claves = [normalizar(x) for x in cfg.get("palabras_clave", [])]
        self.excluir = [normalizar(x) for x in cfg.get("excluir", [])]
        self.regiones = [normalizar(x) for x in cfg.get("regiones", [])]
        self.organismos = [normalizar(x) for x in cfg.get("organismos", [])]
        DATOS.mkdir(exist_ok=True)
        lic = json.loads(ARCHIVO_LICITACIONES.read_text("utf-8")) if ARCHIVO_LICITACIONES.exists() else {}
        est = json.loads(ARCHIVO_ESTADO.read_text("utf-8")) if ARCHIVO_ESTADO.exists() else {}
        self.licitaciones = {l["codigo"]: l for l in lic.get("licitaciones", [])}
        self.dias_revisados = set(est.get("dias_revisados", []))
        self.descartadas = set(est.get("descartadas", []))
        # Prefijo del código (unidad de compra) -> True si está en la zona configurada.
        # Permite omitir sin consultar el detalle las licitaciones de unidades ya vistas fuera de la zona.
        self.unidades = est.get("unidades", {})
        self.clave_filtros = json.dumps([self.regiones, self.organismos])
        if est.get("clave_filtros") != self.clave_filtros:
            self.unidades, self.descartadas = {}, set()  # cambiaron los filtros: reevaluar todo

    def calza_nombre(self, nombre) -> bool:
        n = normalizar(nombre)
        if any(x in n for x in self.excluir):
            return False
        return not self.claves or any(k in n for k in self.claves)

    def calza_comprador(self, r: dict) -> bool:
        region = normalizar(r.get("region"))
        org = normalizar(f"{r.get('organismo')} {r.get('unidad')} {r.get('comuna')}")
        if self.regiones and not any(x in region for x in self.regiones):
            return False
        return not self.organismos or any(x in org for x in self.organismos)

    @staticmethod
    def unidad(codigo: str) -> str:
        return str(codigo or "").split("-")[0]

    def omitir(self, codigo: str) -> bool:
        return codigo in self.descartadas or self.unidades.get(self.unidad(codigo)) is False

    def procesar(self, codigo: str, origen: str) -> bool:
        d = self.api.detalle(codigo)
        if not d:
            return False
        r = aplanar(d, self.licitaciones.get(codigo), origen)
        en_zona = self.calza_comprador(r)
        self.unidades[self.unidad(codigo)] = en_zona
        if en_zona:
            self.licitaciones[codigo] = r
            return True
        self.licitaciones.pop(codigo, None)
        self.descartadas.add(codigo)
        return False

    def guardar(self):
        orden = sorted(self.licitaciones.values(), key=lambda r: r.get("cierre") or "", reverse=True)
        ARCHIVO_LICITACIONES.write_text(json.dumps({
            "actualizado": datetime.now().isoformat(timespec="seconds"),
            "filtros": {"palabras_clave": self.cfg.get("palabras_clave", []), "regiones": self.cfg.get("regiones", []),
                        "organismos": self.cfg.get("organismos", [])},
            "licitaciones": orden,
        }, ensure_ascii=False, separators=(",", ":")), "utf-8")
        ARCHIVO_ESTADO.write_text(json.dumps({
            "clave_filtros": self.clave_filtros, "dias_revisados": sorted(self.dias_revisados),
            "unidades": self.unidades, "descartadas": sorted(self.descartadas),
        }, ensure_ascii=False, indent=0), "utf-8")

    def vigilar(self):
        print("Oportunidades: descargando licitaciones activas…")
        activas = self.api.activas()
        codigos_activos = {l.get("CodigoExterno") for l in activas}
        cand = [l["CodigoExterno"] for l in activas
                if self.calza_nombre(l.get("Nombre")) and not self.omitir(l.get("CodigoExterno"))]
        print(f"  {len(activas)} activas en el país, {len(cand)} calzan con las palabras clave")
        n = 0
        for i, c in enumerate(cand, 1):
            n += self.procesar(c, "vigilancia")
            if i % 20 == 0:
                self.guardar()
        # Las que estaban publicadas y ya no aparecen activas se refrescan para conocer su estado.
        for c, r in list(self.licitaciones.items()):
            if r["estado_cod"] == 5 and c not in codigos_activos:
                self.procesar(c, "vigilancia")
        self.guardar()
        print(f"  {n} oportunidades en la zona configurada")

    def historico(self, dias: int, tope_min: float):
        hoy = date.today()
        pendientes = sorted(
            d for d in (hoy - timedelta(days=k) for k in range(1, dias + 1))
            if d.isoformat() not in self.dias_revisados or (hoy - d).days <= 15
        )
        print(f"Histórico: {len(pendientes)} días por revisar")
        n = 0
        for dia in pendientes:
            if minutos() > tope_min:
                print("  Tope de tiempo alcanzado: el resto queda para la próxima ejecución.")
                break
            for l in self.api.por_fecha(dia, "adjudicada"):
                c = l.get("CodigoExterno")
                if not self.calza_nombre(l.get("Nombre")) or self.omitir(c):
                    continue
                if self.licitaciones.get(c, {}).get("estado_cod") == 8:
                    continue
                n += self.procesar(c, "historico")
            self.dias_revisados.add(dia.isoformat())
            self.guardar()
            print(f"  {dia:%d-%m-%Y} listo · adjudicadas agregadas: {n}")


def main():
    ticket = os.environ.get("MP_TICKET", "").strip()
    if not ticket:
        sys.exit("Falta el ticket: define MP_TICKET (en GitHub: Settings > Secrets and variables > Actions).")
    cfg = json.loads((RAIZ / "config.json").read_text("utf-8"))
    dias = int(os.environ.get("DIAS") or cfg.get("dias_historico", 90))
    tope = float(os.environ.get("MAX_MINUTOS") or 240)
    api = API(ticket, float(cfg.get("pausa_segundos", 1.5)))
    radar = Radar(cfg, api)
    try:
        radar.vigilar()
        radar.historico(dias, tope)
    except ErrorAPI as e:
        radar.guardar()
        sys.exit(f"Error de la API: {e}")
    finally:
        print(f"Consultas realizadas: {api.consultas} · {minutos():.1f} min")


if __name__ == "__main__":
    main()
