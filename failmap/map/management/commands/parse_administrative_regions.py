# pylint: disable=C0321
import logging
import re
from typing import List

from django.core.management.base import BaseCommand
from iso3166 import countries

from failmap.map.models import AdministrativeRegion
from failmap.organizations.models import OrganizationType

log = logging.getLogger(__package__)

# Below is a heavily edited list of the OSM administrative region page. It's molded so that spellings of
# near-the-same stuff has the same spelling. It is an approximation of all regions in the world, which constantly
# change. It's possible some things are identified as multiple of the same. It's your choice to see what you
# want to import and show on the map. The supplied list is here for convenience only

ten_Region = """
|-
| '''{{Flagicon|Afghanistan}}'''<br /> <small>''(proposed)''</small>
| N/A
| province
| N/A
| district
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Albania}}'''<br /> <small>''(proposed)''</small>
| N/A
| [[wikipedia:Category:NUTS 2 statistical Region of Albania|NUTS-2 Region of Albania]] <small>non-administrative Region,
| N/A
| county
| district
| municipality
| Neighborhood
| N/A
|-
| '''{{Flagicon|Algeria}}'''<br /> <small>''(proposed)''</small>
| N/A
| province
| N/A
| district
| N/A
| commune
| N/A
| N/A
|-
| '''{{Flagicon|Andorra}}'''<br /> <small>''(proposed)''</small>
| N/A
| N/A
| N/A
| N/A
| parish
| municipality
| N/A
| N/A
|-
| '''{{Flagicon|Antigua and Barbuda}}'''<br /> <small>''(proposed)''</small>
| N/A
| [[wikipedia:parish and dependencies of Antigua and Barbuda|parish and dependencies]] borders
| N/A
| N/A
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Argentina}}'''<br /> <small>''(proposed)''</small>
| N/A
| Province
| Department
| District
| municipality
| Village, City, town
| Barrio
| N/A
|-
| '''{{Flagicon|Aruba}}'''<br /> <small>''(proposed)''</small>
| N/A
| N/A
| N/A
| N/A
| N/A
| municipality
| N/A
| N/A
|-
| '''{{Flagicon|Australia}}'''<br /> <small>''(proposed)''</small>
| N/A
| State or Territory Border
| N/A
| Local Government Authority Border(e.g Shire/Council)
| district
| Postcode Border (used for GIS and census)
| Suburb and Locality Border (If larger than ABS boundary)
| Suburb and Locality Border (ABS boundaries)
|-
| '''{{Flagicon|Austria}}'''
| (NUTS1 - macht in AT null Sinn)
| [[wikipedia:de:Land (Österreich)|Bundesland]]<br>NUTS2
| (NUTS3 - macht in AT wenig Sinn)
| [[wikipedia:de:Liste der Bezirke und Statutarstädte in Österreich|Politischer Bezirk]]<br>Gemeindekennzahl: xxx
| N/A
| [[wikipedia:de:Gemeinden in Österreich nach Bundesland|Gemeinde]]<br>Gemeindekennzahl: xxxyy<br>LAU-2
| [[wikipedia:de:Gemeindebezirk|Wiener]] / [[wikipedia:de:Kategorie:Stadtbezirk von Graz|Grazer]] / ... Stadt- / Gemeind
| (opt.) Stadtteile
|-
| '''{{Flagicon|Azerbaijan}}'''<br /> <small>''(proposed)''</small>
| disputed territory - unrecognized state (Nagorno-Karabakh Republic)
| autonomous republic (Nakhchivan Autonomous Republic)
| Region ({{lang|az|rayons}}) and cities with authority of republic level ({{lang|az|şəhərlər}})
| N/A
| N/A
| municipality ({{lang|az|bələdiyyələr}})
| N/A
| N/A
|-
| '''{{Flagicon|Bahamas}}'''<br /> <small>''(proposed)''</small>
| N/A
| N/A
| N/A
| Central government district - [[wikipedia:en:New Providence|New Providence]] only
| N/A
| [[wikipedia:en:Local government in the Bahamas#district of The Bahamas|district of the Bahamas (Local government)]]
| N/A
| N/A
|-
| '''{{Flagicon|Bahrain}}'''<br /> <small>''(proposed)''</small>
| N/A
| Governorate
| N/A
| Municipality Example: Al Manamah, Ras Rumman etc
| N/A
| N/A
| neighbourhood
| N/A
|-
| '''{{Flagicon|Bangladesh}}'''<br /> <small>''(proposed)<br /> (see also [[wikipedia:Administrative geography of Bangla
| [[wikipedia:Divisions of Bangladesh|Division]]
| N/A
| [[wikipedia:district of Bangladesh|District]]
| [[wikipedia:Upazilas of Bangladesh|Subdistrict]] (Upazila / Thana)
| [[wikipedia:List of City Corporations of Bangladesh|City Corporation]]
| [[wikipedia:List of Municipal Corporations of Bangladesh|Municipal Corporation]] / Pourashava
| [[wikipedia:Unions of Bangladesh|Union]]
| N/A
|-
|-
| '''{{Flagicon|Barbados}}'''<br /> <small>''(proposed)''</small>
| National Border (Island coastline)
| N/A
| N/A
| [[wikipedia:parish of Barbados|parish of Barbados]]
| N/A
| N/A
| Suburbs, Hamlets and Village
| Neighbourhoods, Housing Developments
|-
| '''{{Flagicon|Belarus}}'''<br /> <small>''(proposed)''</small>
| N/A
| Oblasts (вобласьць / область)
| N/A
| Region (раён / район)
| N/A
| Soviets of settlement (сельсавет / cельсовет)
| Suburbs (раён гораду / район города)
| municipality (населены пункт / населённый пункт)
|-
| '''{{Flagicon|Belgium}}'''<br /> <small>''([[WikiProject Belgium/Boundaries|proposed / in use]])''</small>
| <small>(see {{Tag|boundary|political}} for linguistic communities)</small>
| region
| N/A
| [[wikipedia:Province of Belgium|province]] (NUTS2)
| [[wikipedia:Arrondissements of Belgium|Administrative arrondissements]] (NUTS3)
| [[wikipedia:Municipality of Belgium|municipality]]
| Deelgemeenten (''sections'')
| N/A
|-
| '''{{Flagicon|Belize}}'''
| N/A
| [[wikipedia:District of Belize|district]]
| N/A
| N/A
| N/A
| [[wikipedia:List of municipality in Belize#Cities and towns|Cities and towns]]
| N/A
| N/A
|-
| '''{{Flagicon|Benin}}'''
| N/A
| {{Wikipedia|text=no|fr|Département du Bénin|Département}}
| N/A
| {{Wikipedia|text=no|fr|Department du Bénin|Commune}}
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Bhutan}}'''<br /><small>''(proposed by [[User:ff5722|ff5722]])''</small>
| N/A
| [[wikipedia:Dzongkhag|Dzongkhag]]
| [[wikipedia:Dungkhag|Dungkhag]]
| [[wikipedia:Gewogs of Bhutan|Gewog]]
| [[wikipedia:Thromde|Thromde]]
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Bosnia and Herzegovina}}'''<br /> <small>''([[WikiProject Bosnia and Herzegovina/Administrativne granice
| N/A
| entitet / eнтитет / entity<br>distrikt / дистрикт / district
[http://pastebin.com/raw.php?i=CDpR9Tvg napomena / напомена / note]
| kanton (FBiH) / županija (FBiH) / кантон (ФБиХ) / canton (FBiH)
| grad / град / city
| općina / opština / општина / muncipality<br>
| mjesna zajednica / мјесна заједницa / locality combinations
| naselje / насеље / localities
| N/A
|-
| '''{{Flagicon|Brazil}}'''
| Regiões (Sul, Sudeste, Centro-Oeste, Norte, Nordeste)<br /> ''(Region)''
| Unidades Federativas (Estados e district Federal)<br /> ''(states and Federal District)''
| [[wikipedia:pt:Mesorregiões|Mesorregiões]]<br /> ''(meso-Region)''
| Regiões metropolitanas<br /> ''(metropolitan areas)''
| [[wikipedia:pt:Microrregiões|Microrregiões]]<br /> ''(micro-Region)''
| Municípios e regiões administrativas do district Federal<br /> ''(municipality and administrative Region of the Federa
| districts e Sub-Prefeituras<br /> ''(district)''
| Bairros e Sub-districts<br /> ''(suburbs and neighborhoods)''
|-
| '''{{Flagicon|Brunei}}'''<br /> <small>''(proposed by [[User:Zulfadli51]])''</small>
| N/A
| [[Wikipedia:district of Brunei|district]] ''(daerah)''
| N/A
| [[Wikipedia:Mukims of Brunei|Mukims]] (subdistrict)
| N/A
| [[Wikipedia:Village of Brunei|Village]] ''(kampung'' or ''kampong)'', as designated by the Survey Department
| N/A
| N/A
|-
| '''{{Flagicon|Bulgaria}}'''
| N/A
| Planning Region NUTS 2 (Райони за планиране /за Евростат/)
| N/A
| Region (Области)
| Мunicipalities (Общини)
| Borders of city, town, village (кметства, землища, райони)
| district and suburbs (Квартали и предградия)
| Suburb parts, neighborhoods (Части от квартали, махали)
|-
| '''{{Flagicon|Burkina Faso}}'''<br /> <small>''([[WikiProject Burkina Faso/subdivisions|proposed]])''</small>
| N/A
| Region
| province
| Department/commune
| Arrondissements (only in the 2 cities of [[Ouagadougou]], and [[Bobo Dioulasso]])
| Towns or Village (excluding their surrounding rural areas)
| Urban sectors (only in cities, and in the capital town of other urban municipality)
| N/A
|-
| '''{{Flagicon|Burundi}}'''<br /> <small>''([[WikiProject Burundi/Boundaries|proposed]] by [[User:Arie Scheffer|Arie Sc
| N/A
| province
| N/A
| commune
| N/A
| Collines
| N/A
| Sous-Collines
|-
| '''{{Flagicon|Canada}}'''<br /> <small>''Varies by province; see [[Canada admin level]].''</small>
| {{n/a}}
| province & territories
| Major divisions (only some province) & first nation territories
| Regional municipality & single-tier municipality
| {{n/a}}
| Populated areas within rural municipality & boroughs/arrondissements within cities
| {{n/a}}
| Neighborhoods
|-
| '''{{Flagicon|Cameroon}}'''
| N/A
| Region, like Extrême-Nord (similar to NUTS2)
| N/A
| Department, like Mayo-Danay (similar to NUTS3)
| Arrondissements, like Njombe Penja
| commune, like Melong. Use name=* to indicate the name of the commune.
| N/A
| Non-offical quartiers?
|-
| '''{{Flagicon|the Central African Republic}}'''<br /> <small>''(proposed)''</small>
| N/A
| [[wikipedia:Prefectures of the Central African Republic|Préfectures]], like Ouham
| N/A
| [[wikipedia:Sub-prefectures of the Central African Republic|Sous-préfectures]], like Bouca
| commune?
| Arrondisements?
| Quartiers?
| Sub-quartiers?
|-
| '''{{Flagicon|Chad}}'''<br /> <small>''(proposed by [[User:pedrito1414|Pete Masters]])<br /> See also [[wikipedia:Chad
| N/A
| Region (23)
| N/A
| Départments (61)
| Sous-préfectures (200)
| Cantons (446)
| Village ou localités
| Quartiers (subdivisions internes au village)
|-
| '''{{Flagicon|Colombia}}'''
| Región<ref>[[w:s:es:Constitución de Colombia de 1991#Capítulo II: Del régimen departamental|Artículo 306 de la Constit
| Departamento
| [[wikipedia:es:Anexo:Provincias de Colombia|Provincia]]
| Municipio
| Urbano: ciudad
Rural: corregimiento
| Urbano: localidad / comuna
Rural: vereda
| Urbano: barrio
Rural: N/A
| N/A
|-
| '''{{Flagicon|Costa Rica}}'''
| -
| [[wikipedia:es:Organización_territorial_de_Costa_Rica|Provincia]]
| -
| [[wikipedia:es:Cantones_de_Costa_Rica|Cantón]]
| -
| [[wikipedia:es:districts_de_Costa_Rica|district]]
| -
| Barrio
|-
| '''{{Flagicon|Chile}}'''
| N/A
| ''Regiones''
| N/A
| ''Provincias''
| N/A
| ''Comunas''
| N/A
| N/A
|-
| '''{{Flagicon|Croatia}}'''<br /> <small>''(see [[w:hr:Hrvatska#Upravna podjela|Upravna podjela]])'</small>
| N/A
| N/A
| Statistical Region (hr: ''statističke regije'') (Slavonija, Dalmacija,...)
| County (hr: ''županije'')
| municipality borders (hr: ''općine ili gradovi'')
| Settlements (hr: ''naselja'')
| Suburbs (hr: ''granice gradskih četvrti ili kotareva'')
| Suburb parts (hr: ''granice kvartova ili mjesnih odbora'')
|-
| '''{{Flagicon|China}}'''<br /> <small>''(proposed by [[User:Esperanza]])''</small>
| SARs / 特别行政区界线
| province / 省级行政区
| Prefectures / 地级行政区
| County / 县级行政区
| N/A
| Township / 乡级行政区<br>Town / 镇<br>Subdistrict / 街道
| N/A
| Village / 村级自治组织<br>Neighbourhood community / 社区
|-
| &nbsp;&nbsp;'''{{Flagicon|Hong Kong}}'''<br /> <small>''(proposed by [[User:miklcct]])''</small>
| SAR border
| N/A
| Hong Kong / Kowloon / New Territories
| district
| N/A
| N/A
| N/A
| N/A
|-
| &nbsp;&nbsp;'''{{Flagicon|Macau}}'''<br /> <small>''(proposed by [[User:miklcct]])''</small>
| SAR border
| N/A
| Macau / Coloane / Taipa / Cotai
| Freguesias
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Cuba}}'''<br /> <small>''(proposed by [[User:Ricky75]], [[User:Carluti]])''</small>
| N/A
| Provincia
| N/A
| Municipio
| N/A
| Ciudades
| N/A
| Barrios
|-
| '''{{Flagicon|Cyprus}} / Κύπρος / Kıbrıs'''<br /> <small>''(second draft proposal)''</small>
| ''De facto'' partitions: * [[wikipedia:Cyprus|Republic of Cyprus]] (RoC) * [[wikipedia:Northern Cyprus|Turkish Republi
| N/A
| N/A
| The 6 [[wikipedia:district of Cyprus|district]] (e.g. left district (el:)Λάρνακα, en:Larnaca; right district (el:)Λεμε
| N/A
| municipality
| N/A
| N/A
|-
| '''{{Flagicon|Czech Republic}}'''
| N/A
| Statistic Region (NUTS 2)
| N/A
| Region (kraj) (NUTS 3)
| district (okres) (LAU 1)
| Towns / Village (obec) (LAU 2)
| N/A
| Cadastral places (katastrální území)
|-
| '''{{Flagicon|Democratic Republic of the Congo}}'''<br /> <small>''(proposed by [[User:Claire Halleux|clairedelune]])'
| N/A
| Province (26)
| "Ancienne" province
| Territoire / Ville
| Collectivité (secteur, chefferie, cité) / Commune
| Groupement / Quartier
| Localité ou village (terroir) / Cellule
| Subdivision interne au village / Bloc
|-
| '''{{Flagicon|Denmark}}'''<br /> <small>''(proposed)''</small>
| N/A
| Regioner (Region - administrative unit)
| N/A
| N/A
| Kommune (municipality)
| N/A
| N/A
| Sogn (parish)
|-
| '''{{Flagicon|Dominican Republic}}'''<br /> <small>''([[WikiProject Dominican Republic#Boundaries|proposed]])''</small
| N/A
| Province (Provincia)
| N/A
| Municipality (Municipio)
| N/A
| District (district municipal)
| N/A
| N/A
|-
| '''{{Flagicon|Ecuador}}'''<br /> <small>''(proposed by [[User:Temporalista|Temporalista]])''</small>
| N/A
| Provincia
| N/A
| Cantón
| Límite Urbano (ciudades)
| Parroquia Urbana
| Barrio (Urbano), Comunidad (Rural)
| N/A (¿sectores censales?)
|-
| '''{{Flagicon|Egypt}}'''<br /> <small>''(proposed by [[User:Metehyi|Metehyi]])''</small>
| Governorate (Mouhafazah محافظة)
| fixme
| fixme
| fixme
| fixme
| fixme
| fixme
| fixme
|-
| '''{{Flagicon|El Salvador}}'''<br /> <small>''(proposed by [[User:AragonChristopherR17z|AragonChristopherR17z]])''</sm
| fixme
| Departamento
| district
| Municipio
| Cantón
| Barrio
| Colonia
| fixme
|-
| '''{{Flagicon|Equatorial Guinea}}'''<br /> <small>''(proposed by [[User:johanemilsson|johanemilsson]])''</small>
| Regiones (Insular Region and Continental Region)
| Provincias
| N/A
| district
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Estonia}}'''<br /> <small>''([[Talk:WikiProject Estonia#admin_level|proposed]])''</small>
| N/A
| N/A
| N/A
| Countys (''maakonnad'')
| municipality (''vallad, omavalitsuslikud linnad'')
| Municipality district (''osavallad, linnaosad'')
| Settlement units (''külad, alevikud, alevid, vallasisesed linnad, asumid'')
| N/A
|-
| '''{{Flagicon|Ethiopia}}'''<br /> <small>''(proposed by [[User:Ukundji|Ukundji]])''</small>
| N/A
| Administrative States (9)
| Zones (68+2)
| Woreda (550+6)
| N/A
| Kebele
| N/A
| Village (Gots)
|-
| '''{{Flagicon|Finland}}'''<br /> <small>''(proposed by [[User:Boozeman|Boozeman]], augmented by [[User:Skela|Skela]])'
| Main areas (Pääalueet, [[wikipedia:fi:NUTS:FI|NUTS]] 1): Manner-Suomi
| province (AVIn toimialueet (ent. läänit), [[wikipedia:fi:NUTS:FI|NUTS]] 2): [//www.openstreetmap.org/browse/relation/3
| N/A
| Region (Maakunnat, [[wikipedia:fi:NUTS:FI|NUTS]] 3): [//www.openstreetmap.org/browse/relation/37355 Uusimaa]
| Sub-Region (Seutukunnat, [[wikipedia:fi:LAU:FI|LAU]] 1): [//www.openstreetmap.org/browse/relation/38101 Helsingin seut
| municipality (Kunnat / Kaupungit, [[wikipedia:fi:LAU:FI|LAU]] 2, <small>for ref=*, see [http://www.vrk.fi/ Väestörekis
| Village (kylät), Kaupunginosien suuralueet (Helsinki; Espoo, Vantaa ...)
| suburbs (Kaupunginosat): [//www.openstreetmap.org/browse/relation/188175 Kulosaari]
|-
| '''{{Flagicon|France}}'''<br /> <small>([[WikiProject France/Tracer les limites administratives|in use]])''</small>
| Territorial areas<br /> <small>''(non purely administrative: one for Metropolitan France including Corsica, and one fo
| Region<br /> <small>''(note: 7 Region have replaced the 16 former Region still used by NUTS2 and ISO3166-2)''</small>
| Circonscription départementale<br /> <small>''(replacing a splitted former department, for the préfecture of Rhône, st
| Department<br /> <small>''(similar to NUTS3 and ISO3166-2), including the new department of Rhône (a sous-préfecture)<
| Arrondissements<br /> <small>''(subdivision of departements around a sous-préfecture)<br /> (note: previously used for
| commune<br /> <small>''Use name=* to indicate the name of the commune, and ref:INSEE=* to indicate the unique identifi
| Arrondissements municipaux (in Paris, Lyon, Marseille only), or commune associées and commune déléguées (in partially
| Quartiers<br /> <small>''(used for the local democracy).<br /> May also be subvidided at level 11 into micro-quartiers
|-
| &nbsp;•&nbsp;'''{{Flagicon|French Polynesia}}'''
| The overseas collectivity
| N/A
| N/A
| Administratrive divisions (archipelagos or sub-archipelagos)
| N/A
| commune (ex. Mo’orea - Mai’ao, ’Ārue, etc.)
| district or atolls
| islands of an atoll or Village in larger islands
|-
| '''{{Flagicon|Gabon}}'''<br /> <small>''(proposed by [[User:johanemilsson|johanemilsson]])''</small>
| N/A
| province
| N/A
| Departments
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Gambia}}'''<br /> <small>''(proposed by [[User:kalc|kalc]] 7 May 2017)''</small>
| N/A
| [[wikipedia:Subdivisions of the Gambia|Region (Divisions)]]
| [[wikipedia:Local government areas of the Gambia|LGAs]]
| [[wikipedia:district of the Gambia|district]]
|
|
|
|
|-
| '''{{Flagicon|Georgia}}'''<br /> <small>''(see also [[Administrative Divisions of Georgia]])''</small>
| Disputed territories - partially recognized states (Abkhazia and South Ossetia)
| Region (მხარე) including the Ajaran Autonomous Republic (ავტონომიური რესპუბლიკა)
| N/A
| district (რაიონი)
| N/A
| N/A
| City Raions in Tbilisi and Batumi
| N/A
|-
|rowspan="2"| '''{{Flagicon|Germany}}'''<br /> <small>''(see also [[de:Grenze|Grenzen in Deutschland]])''</small>
| N/A
| ''federal states border'' (Bundesland) (NUTS 1)
| ''state-district border'' (Regierungsbezirk) (NUTS 2)
| ''county borders'' (Landkreis / Kreis / kreisfreie Stadt / Stadtkreis) (NUTS 3)
| ''[[wikipedia:Amt (administrative division)|amt]]'' (Amtsgemeinde, Verwaltungsgemeinschaft) (LAU 1)
| ''Towns, municipality / City-district'' (Stadt, Gemeinde) (LAU 2)
| '' Parts of a municipality with parish councils / self government'' (Stadtbezirk / Gemeindeteil mit Selbstverwaltung)
| '' Parts of a municipality without ...'' (Stadtteil / Gemeindeteil ohne Selbstverwaltung)
|-
|colspan="8"| ''Umgestellt Dez. 2008 / levels changed Dec. 2008 ([[Talk:Key:boundary#Use of border types in Germany 2|si
|-
| '''{{Flagicon|Ghana}}'''<br /> <small>''(proposed)''</small>
| N/A
| [[wikipedia:Region of Ghana|Region]]
| N/A
| [[wikipedia:district of Ghana|District]]
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Guinea}}''' - Guinée<br /> <small>''(proposed / used)''</small>
| N/A
| [[wikipedia:Region of Guinea|Region]]
| N/A
| [[wikipedia:Prefectures of Guinea|Prefectures]]
| N/A
| [[wikipedia:Sub-prefectures of Guinea|Sub-prefectures (commune)]]
| Village / Towns
| Quartiers (Neighbourhoods)
|-
| '''{{Flagicon|Greece}}'''<br /> <small>''(proposed)''</small>
| N/A
| Όρια {{Wikipedia|el|icon=no|text=no|Αποκεντρωμένες διοικήσεις της Ελλάδας|Αποκεντρωμένων Διοικήσεων}}
| Όρια {{Wikipedia|el|icon=no|text=no|Περιφέρειες της Ελλάδας|Περιφερειών}} (NUTS 2)
| Όρια {{Wikipedia|el|icon=no|text=no|Περιφερειακές ενότητες της Ελλάδας|Περιφερειακών ενοτήτων}} (NUTS 3)
| Όρια {{Wikipedia|el|icon=no|text=no|Δήμοι της Ελλάδας|Δήμων}} (LAU 1)
| Όρια {{Wikipedia|el|icon=no|text=no|Δημοτική ενότητα|Δημοτικών ενοτήτων}} (LAU 2)
| Όρια δημοτικών και τοπικών {{Wikipedia|el|icon=no|text=no|Κοινότητα (τοπική αυτοδιοίκηση)|κοινοτήτων}}
| N/A
|-
| '''{{Flagicon|Guatemala}}'''<br /> <small>''(proposed --[[User:Setian|Esteban Ortiz]] 21 June 2009 (UTC))''</small>
| N/A
| State border ''(Department)''
| N/A
| Municipal border ''(Municipality)''
| N/A
| City and town border ''(Zonas)''
| N/A
| N/A
|-
| '''{{Flagicon|Haiti}}''' (Republic of)<br /> <small>''(proposed --[[User:Vsandre|Vsandre]] 16:19, 15 January 2010 (UTC
| N/A
| State border ''(Department)'' (Layer 1)
| district ''(Arrondissements)''
| Search-And-Rescue sectors ('''temporary''')
| N/A
| City and town border ''(commune)'' (Layer 2)
| N/A
| Suburbs ''(sections)'' (Layer 3)
|-
| '''{{Flagicon|Honduras}}'''<br /> <small>''(proposed --[[User:antoniolocandro|Antonio Locandro]] 11 March 2014)''</sma
| N/A
| ''Department'' (State Border)
| N/A
| ''Municipality'' (Municipal Border)
| N/A
| ''Aldeas'' (Admin level border which encompass several towns / cities)
| ''Ciudades'' (Cities)
| ''Barrios y Colonias'' (Neighborhoods)
|-
| '''{{Flagicon|Hungary}}'''<br /> <small>''(proposed / used)''</small>
| N/A
| Országrészek ''(Groups of Region, NUTS 1)''
| Régiók ''(Region, NUTS 2)''
| Megyék / főváros ''(Counties / capital city, NUTS 3)''
| Kistérségek, járások ''(LAU 1)''
| Települések ''(LAU 2)''
| Kerületek ''(district)''
| N/A
|-
| '''{{Flagicon|Iceland}}'''
| N/A
| N/A
| [[wikipedia:en:Region of Iceland|Region]]
| [[:Image:Sveitarfélög-landsvæði.png|Sveitarfélög]] - ''municipality''
| N/A
| N/A
| N/A
| Hverfi (Suburb)
|-
| '''{{Flagicon|India}}'''<br /> <small>''(see also [[wikipedia:Administrative divisions of India|administrative divisio
| Division
| State
| [[wikipedia:List of district of India|District]]
| Subdistrict (Tehsil / Mandal / Taluk)
| Metropolitan Area
| Municipal Corporation / Municipality / City Council
| Civic Zone
| Village/Civic Ward
|-
| '''{{Flagicon|Indonesia}}'''
| N/A
| Province
| City / Regency (Kotamadya / Kabupaten)
| Subdistrict (Kecamatan)
| Village (Kelurahan / Desa)
| Hamlet (Dusun)
| Community Group (Rukun Warga)
| Neighborhood Unit (Rukun Tetangga)
|-
| '''{{Flagicon|Iraq}}'''<br /> <small>''(proposed by [[User:johanemilsson|johanemilsson]], modified [[User:Øukasz|Øukas
| [[wikipedia:Iraqi Kurdistan|Iraqi Kurdistan]] (Arbil, Duhok, Sulaymaniyah) region
| governorates (muḥāfażah)
|
| district (qadha)
| subdistrict (nahya)
| boroughs (hay) in urban and counties (mukataa) in rural areas
| neighbourhoods (mahalla) in urban and Village (qarya) in rural areas
|
|-
| '''{{Flagicon|Iran}}'''
| N/A
| Province (استان/Ostan)
| N/A
| Counties (شهرستان/Sharestan)
| District (بخش/Bakhsh)
| City (شهر/ Shahr), municipality or rural agglomeration (دهستان/ Dehestan)
| Village (روستا/Rousta)
| Neighborhood Unit (محله/Mahale)
|-
| '''{{Flagicon|Ireland}}'''
| N/A
| Reserved for compatibility with UK states (eg Northern Ireland)
| Province
| County
| Adminstrative County, County City
| Borough & Town council, Dublin Postal district
| Electoral Division
| Townland
|-
| '''{{Flagicon|Isle of Man}}'''
| N/A
| N/A
| N/A
| Sheedings
| N/A
| Parish / Village / Town
| N/A
| N/A
|-
| '''{{Flagicon|Israel}}'''
| הרשות הפלסטינאית<br />Palestinian Authority
| [[wikipedia:he:מחוזות_ישראל|מחוז]]<br />District
| [[wikipedia:he:מחוזות_ישראל|נפה]]<br />Sub-district
| אזור טבעי<br />Natural Region
| [[wikipedia:he:מטרופולין|מטרופולין]]<br />Metropolitan area
| [[wikipedia:he:ערים_בישראל|עיר]], [[wikipedia:he:מועצה_אזורית|מועצה אזוריות]], [[wikipedia:he:מועצה_מקומית|מועצה מקומי
| רובע<br />Borough
| שכונה<br />Neighborhood
|-
| '''{{Flagicon|Italy}}'''<br /> <small>''(as discussed on the Italian Mailing list Vol 16, Issue 27, [[User:Dieterdreis
| N/A
| per i confini regionali (en: boundary of Region)
| N/A
| per i confini provinciali (en: boundary of province)
| N/A
| per i confini comunali (en: boundary of municipality)
| N/A
| per le circoscrizioni (dove sono rimaste) o per le località (en: boundary of district)
|-
| '''{{Flagicon|Côte d'Ivoire}}'''
| N/A
| district<br /> (example: Lagunes) où disctrict autonome (example: Abidjan) <br /> place=state ('''not''' <strike>place
| region<br /> (example: Agnéby-Tiassa) <br /> place=region
| département<br /> (example: Département Sikensi)<br /> place=province
| sous-préfecture<br /> (example: Sous-prefecture Bingerville)<br /><br /> place=county
| commune<br /> (example: Yopougon)
| village<br /> place=village
| quartier
|-
| '''{{Flagicon|Japan}}'''<br /> <small>''(copied from [[Japan tagging#Boundary]])''</small>
| Reserved for [[wikipedia:State (country subdivision)|state]] border - [[wikipedia:ja:道州制|道州制]])
| Prefecture border
| Sub Prefecture border (振興局・支庁 in Hokkaido)
| County (郡)
| Municipal border (Cities, Towns, Village, Special wards of Tokyo)
| Suburb; Wards of cities designated by government ordinance [[wikipedia:ja:政令指定都市|政令指定都市]] , Wards designated
| Quarter; Major Neighbourhood - [[wikipedia:ja:住居表示|大字, (市町村配下の)町]]
| Neighbourhood ; Minor Neighbourhood - [[wikipedia:ja:住居表示|小字, 字, 丁, 丁目]]
|-
| '''{{Flagicon|Jordan}}'''<br /> <small>not implemented below level 4 (governorate)</small>
|
| governorate
|
| district
| subdistrict
|
|
|
|-
| '''{{Flagicon|Kosovo}}'''<br /> <small>''(proposed/used, proposed by [[MarcRKS]] & [[bardhazizi]])''</small>
| N/A
| Komunat e Kosovës
| N/A
| N/A
| N/A
| Zonat Kadastrale
| N/A
| Lagjjet
|-
| '''{{Flagicon|Laos}}'''<br /> <small>''(proposed)''</small>
| N/A
| province (Lao: ແຂວງ khoueng) or one prefecture (kampheng nakhon)
| N/A
| district (Lao: ເມືອງ mɯ́ang)
| Village (Lao: ບ້ານ ban)
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Latvia}}'''<br /> <small>''(proposed)''</small>
| N/A
| N/A
| N/A
| Counties (Novadi), Cities (Republikas nozīmes pilsētas)
| Towns (Pilsētas)
| parish (Pagasti)
| Village (Ciemi)
| Suburbs (Priekšpilsētas)
|-
| '''{{Flagicon|Lebanon}}'''<br /> <small>''(proposed by [[User:Metehyi|Metehyi]] source [http://www.cas.gov.lb/index.ph
| Governorate (Mouhafazah محافظة)
| Qadaa (also known as ''Caza'' قضاء ج. أقضية)
| Federation of municiplalities (إتحاد بلديات)
| Municipality (بلدية)
| منطقة عقاريّة
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Lesotho}}'''<br /> <small>''(proposed by [[User:Htonl|Adrian Frith]])''</small>
| N/A
| district
| N/A
| Constitutencies
| N/A
| Community councils
| N/A
| N/A
|-
| '''{{Flagicon|Liberia}}'''<br /> <small>''(proposed by [[User:edvac|Rafael Ávila Coya]])''</small>
| N/A
| Counties (15)
| N/A
| district (90)
| N/A
| Clans (chiefdoms?)
| N/A
| N/A
|-
| '''{{Flagicon|Libya}}'''<br /> <small>''(proposed by [[User:Jjaf.de|Jano John Akim Franke]])''</small>
| N/A
| district (Shabiya)
| N/A
| N/A
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Lithuania}}'''
| N/A
| Counties (Apskritys)
| municipality (Savivaldybės / Rajonai)
| Eldership (Seniūnijos)
| N/A
| Miestai / miesteliai / Kaimai (Cities / towns / Village)
| N/A
| City/Town suburbs (Miesto / miestelio dalys / miesto seniūnijos)
|-
| '''{{Flagicon|Luxembourg}}'''<br /> <small>''(proposed by [[User:Loll78]])''</small>
| N/A
| district (state)
| Cantons (region)
| commune (county)
| N/A
| Cities / Village (city / town / village)
| Quarters of City (suburb)
|
|-
| '''{{Flagicon|Macedonia}}'''<br /> <small>''(proposed by [[User:borces]])<br /> (see also [[wikipedia:mk:Административ
| N/A
| Статистички Региони (Statistical Region)
| N/A
| Град Скопје (City of Skopje)
| Општини (municipality )
| Град/Село (city / town / village)
| Населби (suburb)
| Маало / Локалитет (neighbourhood / locality)
|-
| '''{{Flagicon|Madagascar}}'''<br /> <small>''([[FR:Madagascar tagging guidelines#Divisions administratives de Madagasc
| Faritany mizakatena (province)
| Faritra (Region)
| N/A
| Distrika (district)
| N/A
| Kaominina (commune)
| N/A
| Fokontany (sections, communities of settlements / townships / Village)
|-
| '''{{Flagicon|Malaysia}}'''
| N/A
| negeri (states)
| bahagian (divisions) ''Sabah & Sarawak only''
| daerah (district)
| subdistrict<br>''[[wikipedia:Kuching District|Kuching District]] only''
| mukim (counties)
| N/A
| PBT, kampung, taman, dll (municipality, including townships, cities, Village, etc.)
|-
| '''{{Flagicon|Malawi}}'''<br /> <small>''(proposed)''</small>
| [[wikipedia:Region of Malawi|Region]]
| [[wikipedia:district of Malawi|district]]
|
| Traditional authorities (rural areas), Urban administrative wards (urban centers)
|
| '''''SC''''' - sub-chiefs governed under the authority of the local traditional authority. The sub-chiefdoms are used
| GVH
| Village
|-
| '''{{Flagicon|Mali}}'''<br /> <small>''(proposed)''</small>
| N/A
| Region
| N/A
| Cercles
| N/A
| Commune
| N/A
| N/A
|-
| '''{{Flagicon|Mauritania}}'''<br /> <small>''(proposed)''</small>
| N/A
| Region (Wilayas)
| N/A
| Department (Moughataa)
| N/A
| Arrondissement
| commune
| N/A
|-
| '''{{Flagicon|Mexico}}'''<br /> <small>''(proposed by [[User:OpenStreetMapMX|OSM México]])<br /> (source: [http://www.
| N/A
| State borders
|
| municipality
|
| city / town limit
| district limits / delegaciones
| city sectors / colonias
|-
| '''{{Flagicon|Moldova}} (Moldova Republic of)'''<br /> <small>''(proposed)''</small>
| disputed territory - unrecognized state ([[wikipedia:ru:Приднестровская_Молдавская_Республика|Pridnestrovian Moldavian
| autonomous Region (Gagauzia and [[wikipedia:ru:Автономное_территориальное_образование_с_особым_статусом_Приднестровье|
| N/A
| region (ro:Raion ru:Район), cities with status of municipius (ro:Municipiu) - Administrative borders
| sectors ({{lang|ro|Sectorul}} {{lang|ru|Сектора}}) of Kishinev
| cities without status of municipiu, commune
| townships, cities, Village, etc.
| borders of suburbs, localities
|-
| '''{{Flagicon|Morocco}}'''<br /> <small>''(proposed)<br /> (See: [[Wikipedia:fr:Organisation territoriale du Maroc|sub
| N/A
| Region (Wilaya)
(جهات المغرب)(ولاية)
| province,<br /> Prefectures (الأقاليم والعمالات)
| Cercles (الدائرة),<br /> Pashalik,<br /> district
| Caïdats (القيادة),<br /> (الإداري) Préfectures d'Arrondissements (عمالات المقاطعات)
| Urban and Rural municipality (الجماعات الحضرية)<br /> and commune (القروية)
| Arrondissements (المقاطعات)
| N/A
|-
| '''{{Flagicon|Mozambique}}'''<br /> <small>''(proposed)<br /> ''</small>
| Region // Regiões (Norte, Centro, Sul)
| province // Províncias
| district OR Province Capital Cities // districts OU Cidades Capitais Provinciais
| Administrative Post // Posto Administrativo
| Headquarters of Administrative Post // Sede do Posto Administrativo
| Neighbourhoods // Bairros
| Blocks // Quarteirões
| Group of 10 houses // Grupo das 10 casas
|-
| '''{{Flagicon|Myanmar}}'''<br /> <small>''(proposed)<br /> (see [[wikipedia:Administrative divisions of Burma|administ
| N/A
| states, Region, union territory, self-administered zones and divisions (ပြည်နယ်, တိုင်းဒေသကြီး, ပြည်တောင်စုနယ်မြေ, ကို
| N/A
| cities (as the only city in Myanmar, Yangon encompasses several district)
| district (cities like Mandalay or Naypyidaw are each one district) (ခရိုင်)
| townships, city-district (မြို့နယ်)
| subtownships
| Village
|-
| '''{{Flagicon|Nepal}}'''<br /> <small>''(proposed)''</small>
| Province
| Development Region
| Zones
| district
| municipality, Sub-municipality and Metropolitans (Nepali: नगरपालिका, उप-महानगरपालिका, महानगरपालिका )
| Cities/Village (This admin level in OSM is what the Nepal Gov. calls a "Village Development Committee" (VDC) (Nepali:
| Ward
| Tole
|-
| '''{{Flagicon|New Zealand}}'''<br /> <small>''(in use --[[User:Sdk|Sdk]] 18 December 2012 (UTC))''</small>
| N/A
| [[wikipedia:Region of New Zealand|Region]] (Canterbury, Bay of Plenty, Auckland, Gisborne etc.) governed by a regional
| N/A
| [[wikipedia:Territorial authorities of New Zealand|district and Cities]] governed by a territorial authority (Dunedin
| N/A
| [[wikipedia:Auckland Council#Local_boards|Local boards in Auckland]]
| N/A
| N/A
|-
| '''{{Flagicon|Nicaragua}}'''<br /> <small>''(proposed)''</small>
| N/A
| Department, such as Chontales and RAACS
| N/A
| Municipality, such as Boaco and Juigalpa
| Indigenous territories, such as Tawira and Mayagna Sauni Bu
| City boundaries, such as Granada and León
| districts, Comarcas, such as district I and El Almacen
| Barrios / Residenciales / Colonias, such as Villa Sandino and Bosques de Altamira
|-
| '''{{Flagicon|Niger}}'''<br /> <small>''(proposed)''</small>
| N/A
| Region
| N/A
| Department
| N/A
| commune
| N/A
| N/A
|-
| '''{{Flagicon|Nigeria}}'''<br /> <small>''(proposed)''</small>
| Geopolitical zones (6)
| States (36) + the federal capital territory
| N/A
| Local Government Areas (774)
| N/A
| Wards (10 to 15 for each LGA - They are like councils)
| N/A
| N/A
|-
| '''{{Flagicon|North Korea}}'''<br /> <small>''(proposed)''</small>
| N/A
| Province (도), Capital city (직할시), Special city (특별시)
| N/A
| County (군), City (시)
| Ward (구역)
| Town (읍), Village (리), Neighbourhood (동), Workers' district (로동자구)
| N/A
| N/A
|-
| '''{{Flagicon|Norway}}'''<br /> <small>''(proposed)''</small>
| N/A
| County (Fylke) (19)<br>(1) Example: Rogaland, Hordaland
| N/A
| N/A
| municipality (Kommue) (430)<br>Example: Stavanger, Sandnes etc
| N/A
| Bydel <br> Example: Røa, Våland, Minde etc
| N/A
|-
| '''{{Flagicon|Paraguay}}'''
| natural Region<br>[[wikipedia:es:Paraguay#Regiones_Naturales|regiones naturales]]
| states<br>Department
| N/A
| N/A
| N/A
| municipal, city limits<br>municipalidades / districts
| N/A
| suburb and locality<br>barrios y compañias rurales
|-
| '''{{Flagicon|Peru}}'''
| N/A
| [[wikipedia:en:Region_of_Peru|States, Departments]]<br>[[wikipedia:es:Department_del_Perú|Department]]
| N/A
| [[wikipedia:en:province_of_Peru|Region, province]]<br>[[wikipedia:es:Provincias_del_Perú|Provincias]]
| N/A
| [[wikipedia:en:district_of_Peru|Counties, district]]<br>[[wikipedia:es:districts_del_Perú|districts]]
| N/A
| suburb and locality<br>Centros Poblados, Caserío, Anexo, Comunidad Nativa, etc
|-
| '''{{Flagicon|the Philippines}}'''<br /> <small>''(first proposed by [[User:Ianlopez1115|Ianlopez1115]], revised by [[
| [[wikipedia:Region of the Philippines|Region]]
| [[wikipedia:province of the Philippines|province]]
| Provincial Legislative district (if any)
| [[wikipedia:Cities of the Philippines|Cities]] and [[wikipedia:municipality of the Philippines|municipality]]
| City/Municipal Legislative district (if any)
| Other administrative district (if any) (proposed: [[wikipedia:Barangay|Barangays]])
| Zones (if any) (proposed: [[wikipedia:Purok|Purok]]/[[wikipedia:Barangay|Sitio]])
| [[wikipedia:Barangay|Barangays]] (proposed: gated communities (i.e. subdivisions) or any other type of community which
|-
|rowspan="2"|'''{{Flagicon|Portugal}}''' <small>''([[WikiProject Portugal/Divisões Administrativas/Lista de Divisões Adm
| N/A
| [[wikipedia:Administrative divisions_of_Portugal#Region|Region]]
| [[wikipedia:List of islands of Portugal#Azores|Island]] / Subregion
| [[wikipedia:district of Portugal|District]]
| [[wikipedia:Administrative divisions of Portugal#municipality|Municipality]]
| [[wikipedia:Administrative divisions of Portugal#Civil parish|Civil parish]]
| Locality
| Neighbourhood
|-
| N/A
| Região
| Ilha / Sub-região
| district
| Concelho
| Freguesia
| Localidade
| Bairro
|-
| '''{{Flagicon|Romania}} (România)'''<br /> <small>''(proposed)''</small>
| Historical province (Transylvania, Moldavia ...)<br /> <small>We don't think they will ever be drawn, as these are not
| Counties (Judeţe) and the Municipality of Bucharest
| N/A
| municipality (Comune), which includes the surrounding area around the city / town / village, see [[wikipedia:ro:Imagin
| N/A
| N/A
| N/A
| N/A
|-<!-- Данная версия была выработана в результате долгих и трудных переговоров. Просьба наобум не править. В случае, есл
|rowspan="2"| '''{{Flagicon|Russia}} (Russian Federation)'''<br/> <small>''([[RU:Key:boundary|details]])''</small>
| <!-- 3 --> [[wikipedia:en:Federal district of Russia|Federal district]]
| <!-- 4 --> [[wikipedia:en:Federal subjects of Russia|Federal subjects]]
| <!-- 5 --> Groups of municipal district / urban okrugs, administrative okrugs / district of federal cities
| <!-- 6 --> Municipal district of federal subjects, municipal urban okrugs
| <!-- 7 --> rowspan=2 | N/A
| <!-- 8 --> Urban and rural municipality, municipal intra-city territories of federal cities
| <!-- 9 --> Administrative district of urban okrugs and municipality
| <!-- 10 --> <small>''(Under discussion: all hamlets / suburbs or only suburbs with local government offices)''</small>
|-
| <!-- 3 --> [[wikipedia:ru:Федеральные округа Российской Федерации|Федеральные округа]]
| <!-- 4 --> [[wikipedia:ru:Федеративное устройство России|Субъекты федерации]]
| <!-- 5 --> Объединения муниципальных районов / городских округов, административные округа / районы городов федеральног
| <!-- 6 --> Муниципальные районы субъектов федерации, муниципальные городские округа
| <!-- 8 --> Городские и сельские муниципальные образования, внутригородские муниципальные территории городов федерально
| <!-- 9 --> Административные районы городских округов и поселений
| <!-- 10 --> <small>''(Обсуждается: все населённые пункты либо только микрорайоны с территориальными управлениями админ
|-
| '''{{Flagicon|Serbia}}'''<br /> <small>''(proposed)<br /> (see [[wikipedia:Administrative divisions of Serbia|Administ
| <!-- 3 --> N/A
| <!-- 4 --> province<br/>покрајине<br/>(future NUTS1?)
| <!-- 5 --> reserved<br/>(NUTS2?)
| <!-- 6 --> district<br/>окрузи<br/>(NUTS3?)
| <!-- 7 --> municipality<br/>општине<br/>(LAU1?)
| <!-- 8 --> settlements<br/>насеља<br/>(LAU2?)
| <!-- 9 --> N/A
| <!-- 10 --> N/A
|-
| '''{{Flagicon|Senegal}}'''<br /> <small>''([[FR:WikiProject Senegal#Frontières administratives|proposed]])''</small>
| <!-- 3 --> boundary of the "Region" like Saint-Louis, Matam...
| <!-- 4 --> N/A
| <!-- 5 --> N/A
| <!-- 6 --> boundaries of the "Department" see a list [[wikipedia:fr:Department du Sénégal|here]]
| <!-- 7 --> boundary of "arrondissements" : subdivision of departements; see a list [[wikipedia:fr:Arrondissements du S
| <!-- 8 --> boundary of commune like Dakar, Tambacounda, Ziguinchor...see a list [[wikipedia:fr:commune du Sénégal#Régi
| <!-- 9 --> boundary of "Arrondissement municipal"
| <!-- 10 --> Used for the local democracy : quartiers
|-
| '''{{Flagicon|Sierra Leone}}'''<br /> <small>''(proposed by [[User:IndoFio|IndoFio]])''</small>
| <!-- 3 --> N/A
| <!-- 4 --> borders of 3 province (Eastern, Northern, and Southern) + Western Area (as described in ISO 3166-2)
| <!-- 5 --> borders of 12 administrative district, 6 municipality (including Freetown), and Western Area Rural
| <!-- 6 --> borders of Paramount Chiefdoms, 8 Wards in Freetown, and 4 district in Western Area
| <!-- 7 --> borders of Section Chiefdoms (Paramount Chiefdoms only)
| <!-- 8 --> N/A
| <!-- 9 --> N/A
| <!-- 10 --> N/A
|-
| '''{{Flagicon|Slovakia}}'''
| NUTS 2 Region (Groups of Region): (''SK: oblasti: Bratislavský kraj, západné Slovensko, stredné Slovensko, východné Sl
| region borders (''SK: hranica kraju, vyššieho územného celku'')
| N/A
| borders of Bratislava and Košice (''SK: hranice miest Bratislava a Košice'')
| N/A
| district borders (''SK: hranica okresu'')
| LAU 2 Obec (Town/Village), autonomous towns in Bratislava and Košice
| Katastrálne územie (Cadastral place) (''SK: katastrálne územie obce'')
|-
| '''{{Flagicon|Slovenia}}'''<br /> <small>''(see [[WikiProject Slovenia/Regije|Regije]] and [[wikipedia:sl:Upravna deli
| NUTS 2 (West-East)
| reserved for regional borders - if they are ever finalized (''SL: pokrajine'')
| borders of statistical Region (''SL: statistične regije'')
| N/A
| ... borders (''SL: upravne enote'')
| Municipal borders (''SL: občine'')
| N/A
| Suburbs, hamlets (''SL: meje naselij'')
|-
| '''{{Flagicon|South Africa}}'''
| N/A
| provincial borders
| N/A
| district borders (borders of district municipality and metropolitan municipality)
| N/A
| municipal borders (borders of local municipality within district)
| N/A
| ward borders
|-
| '''{{Flagicon|South Korea}}''' (ROK)<br /> <small>''(proposed by [[User:Namuori|namuori]] under discussion talk-ko Sep
| N/A
| Regional(State) Border (Metropolitan Self-Governing Entity(MSGE) or 광역자치단체, as per [[wikipedia:ko:대한민국의 행정 구역|대한민국의 행정
| N/A
| County Border (Basic Self-Governing Entity(BSGE) or 기초자치단체 - MSGE's Gu/Gun & Do's Si 특별시의 자치구, 광역시의 자치구/군, 도의 자치시/군)
| City; Within a BSGE (기초자치단체(자치시)의): -gu 구 ; Within a Special Self-governing province (특별자치도의) :-si 시
| Town; Within a -si (시의): -dong 동, -ga 가; Within a -do (도의): -eup 읍 : -myeon 면
| N/A
| Village (-ri, 리), -tong 통
|-
| '''{{Flagicon|South Korea}}''' (merge with above for readability)
| N/A
| Province (-do, 도), Metropolitan City (gwangyeok-si 광역시), Special City (Seoul)(teukbyeol-si 특별시)
| N/A
| County (-gun, 군), City (-si, 시), Basic Self-Governing Entity (BSGE, 기초자치단체)
| District (-gu, 구). Special Self-governing Province (Jeju)(teukbyeol-jachido 특별자치도)
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|South Sudan}}'''<br /> <small>''(proposed by [[User:Claire Halleux|clairedelune]])''</small>
| Historical region (3)
| State (28)
| (Before 2015) State (10)
| County (86)
| Payam (580)
| Boma (2092)
| Village
| Village subdivision (rural) / Block (urban)
|-
| '''{{Flagicon|Spain}}'''<br /> <small>''(proposed)''</small> Frontera nacional.
| (Unused) [[wikipedia:Groups of Spanish autonomous communities|Groups of Spanish autonomous communities]] ([[wikipedia:
| [[wikipedia:Autonomous communities of Spain|Autonomous communities]] ([[wikipedia:NUTS:ES|NUTS 2]]). [[wikipedia:es:Co
| N/A
| [[wikipedia:province of Spain|province]], see {{Tag|boundary|political}} for [[wikipedia:Cabildo insular |insular coun
| [[wikipedia:Comarcas of Spain|Counties]]. [[wikipedia:es:Comarcas de España|Comarcas]].
| [[wikipedia:municipality of Spain|municipality]], equivalent to townships, commune. [[wikipedia:es:Municipality de Esp
| district (parish). [[wikipedia:es:district |district]] ([[wikipedia:es:Entidad colectiva de población |Entidad colecti
| [[wikipedia:Ward (country subdivision)|Wards]]. [[wikipedia:es:Entidad singular de población |Entidad singular de pobl
|-
| '''{{Flagicon|Swaziland}}'''<br /> <small>''(proposed by [[User:Htonl|Adrian Frith]])''</small>
| N/A
| ''Tifundza'' (Region)
| N/A
| ''Tinkhundla'' (constituencies)
| N/A
| ''Imiphakatsi'' (chiefdoms)
| N/A
| N/A
|-
| '''{{Flagicon|Suriname}}'''<br /> <small>''(proposed by [[User:Pander|Pander]])''</small>
| N/A
| [https://nl.wikipedia.org/wiki/Districten_van_Suriname Districten] ([https://en.wikipedia.org/wiki/district_of_Surinam
| N/A
| N/A
| N/A
| [https://nl.wikipedia.org/wiki/Ressort_(Suriname) Ressorten] ([https://en.wikipedia.org/wiki/Resorts_of_Suriname resor
| N/A
| N/A
|-
| '''{{Flagicon|Switzerland}}'''<br /> <small>''(proposed by [[User:Studerap|studerap]], extened by [[User:t-i|t-i]])''<
| N/A
| Cantons (de: Kantone)<br />Example: Aargau, Vaud
| Administrative region or other who isn't a district ([[wikipedia:de:Kanton Bern#Verwaltungskreise und -regionen|de: Ve
| district ([[wikipedia:de:Bezirk (Schweiz)#Liste der Bezirke der Schweiz nach Kantonen|de: Bezirke/Ämter]], fr: distric
| Circles or [[wikipedia:de:Bellinzona (Bezirk)|something other]] between district and municipality.
| municipality (de: Gemeinden/Städte, fr: commune/villes)<br />Example: Basel, Montreux
| Suburbs (de: Stadtkreise/Stadtteile, fr: secteurs)<br />e.g. Kreis 7 (Zurich)
| Quarters (de: Quartiere, fr: quartiers) <br />e.g. Les Pâquis (Geneva)
|-
| '''{{Flagicon|Sweden}}'''
| Landsdel (Region) Example: Norrland, Svealand och Götaland
| Län (County / NUTS3)<br>(21) Example: Västra Götalands län, Örebro län etc
| N/A
| N/A
| Kommun (municipality / LAU2) <br>(290) Example: Göteborg, Alingsås etc
| N/A
| Stadsdelsområde / Stadsdelsnämdsområde (Stockholm / Göteborg) <br> Example: Frölunda, Skarpnäck etc <br>In Umeå, this
| Stadsdel / Primärområde <br> Example: Masthugget, Södermalm etc <br> In Umeå, this is called "Stadsdelsområde" (Backen
|-
| '''{{Flagicon|Syria}}'''<br>(proposed by qa003qa003)
| N/A
| Governorates<br>محافظة<br>muhafazah
| district<br>منطقة<br>mintaqah
| Subdistrict<br>ناحية‎‎<br>nahiya
| N/A
| Cities, towns and Village of Subdistrict<hr />Damascus municipality<br>بلدية<br>baladiyah
| N/A
| Damascus neighborhoods<br>الحي <br>hayy
|-
| '''{{Flagicon|Taiwan}}'''
| N/A
| Province 省; Municipality 直轄市
| District of Municipality 直轄市的區
| Provintial municipality 省轄市; County 縣
| District 省轄市的區
| County-administered city 縣轄市; Township 鄉/鎮
| Village 村/里
| Neighbourhood 鄰
|-
| '''{{Flagicon|Tajikistan}}'''<br /> <small>''(proposed by [[User:Maailma|Maailma]])''</small>
| N/A
| Border of Province (3), Region (1) and Capital city (Sughd Province, Region of Republican Subordination, Khatlon Provi
| N/A
| District (e.g. Varzob, Khovaling, Murghob)
| N/A
| Jamoat (e.g. Sarichashma)
| N/A
| Deha (village) / micro rayons
|-
| '''{{Flagicon|Tanzania}}'''<br /> <small>''(proposed)''</small>
| Zone (e.g. Northern Zone)
| Region (e.g. Arusha)
| District (e.g. Arumeru)
| Division (e.g. Mbarika)
| Ward (e.g. Usa River)
| N/A
| Village (in rural context) or Sub-ward/Mtaa (e.g. USA River; urban)
| Shina (area of responsibility of a Mjumbe or Tencell)
|-
| rowspan="2" | '''{{Flagicon|Thailand}}'''<br /> <small>''([[WikiProject Thailand#Administrative levels|proposed]])''</
| rowspan="2" | N/A
| rowspan="2" | Province /<br>Bangkok
| rowspan="2" | N/A
| rowspan="2" | District /<br>Bangkok: Khet
| rowspan="1" | N/A
| rowspan="1" | Subdistrict /<br>Bangkok: Kwaeng
| rowspan="1" | N/A
| rowspan="1" | Village {{Tag|place|village}}
|-
| colspan="3" | Municipality City {{Tag|place|city}}<br>Municipality Town {{Tag|place|town}}<br>Municipality Township {{
| rowspan="1" | Community <br>{{Tag|place|hamlet}}
|-
| '''{{Flagicon|Togo}}'''<br /> <small>''(proposed)''</small>
| N/A
| Région /<br /> Commune de [[Lomé]] ''(statut particulier)''
| Préfecture<br /> <small>''(note : la préfecture du Golfe, dans la région Maritime, couvre également Lomé)''</small>
| Sous-préfecture<br /> <small>''(note : Lomé est également une sous-préfecture)''</small>
| Commune <small>''(sauf Lomé)''</small>
| Arrondissement municipal
| Quartier
| Village
|-
| '''{{Flagicon|Tunisia}}'''
| N/A
| Borders of the 24 [[wikipedia:Governorates_of_Tunisia|Governorates]] of Tunisia
| Delegations (district) Borders
| Imadats (Sectors) Borders
| N/A
| N/A
| N/A
| N/A
|-
| '''{{Flagicon|Turkey}}''' See [[wikipedia:tr:NUTS|NUTS]] as well
| the Census-defined [[wikipedia:Region of Turkey|geographical Region]] of Turkey (which are used for administrative pur
| Borders of the 81 [[wikipedia:province of Turkey|province]] of Turkey (NUTS 3)
| N/A NUTS 2
| the boundary of [[wikipedia:district of Turkey|district]] (turkish ''ilçe'')
| N/A LAU 1 (aka NUTS 4)
| N/A LAU 2 (aka NUTS 5) (inofficially: boundaries of Village)
| N/A
|
|-
| '''{{Flagicon|Uganda}}'''
| Borders of the [[wikipedia:Region of Uganda|Region]] of Uganda (which do not have any political or administrative impo
| Borders of the 112 [[wikipedia:district of Uganda|district]] of Uganda
|
| the boundary of [[wikipedia:Counties of Uganda|counties]]
| N/A
| the boundary of [[wikipedia:Sub-counties of Uganda|sub-counties]]
| the boundary of parish
| the boundary of Zones (in Kampala only)
|-
| '''{{Flagicon|Ukraine}}'''<br /> <small>''(proposed)''</small>
|
| Crimea, Oblasts / АР Крим, області / АР Крым, области
| N/A
| Crimea rayons, rayons in oblasts / Райони в Криму, райони в областях / Районы в Крыму, районы в областях
| Administrative rayons in cities, towns / Адміністративні райони в містах/ Административные районы в городах
| Local radas in rayons in oblasts or in Crimea / Місцеві ради в районах області або в Криму (міські ради, селищні ради,
| N/A
| N/A
|-
| '''{{Flagicon|United Kingdom}}'''
| N/A
| England, Scotland, Wales and Northern Ireland
| [[wikipedia:Region of England|Region of England]]
| England: [[wikipedia:Metropolitan county|metropolitan counties]], [[wikipedia:Non-metropolitan county|non-metropolitan
| N/A
| England only: district, consisting of [[wikipedia:Metropolitan borough|metropolitan boroughs]], [[wikipedia:London bor
| N/A
| England: [[wikipedia:Civil parish|civil parish]] <br> Scotland: [[wikipedia:Community council#Scotland|community counc
|-
| '''{{Flagicon|United States}}'''<br /> <small>''Simplified/generalized; see [[United_States_admin_level]] and<br />[[W
| There are semi-official and unofficial Region, see {{WikiIcon|List_of_Region_of_the_United_States}}.  These are geogra
| [[United_States_admin_level|the 50 states,<br />three Territories, two Commonwealths<br />and the District of Columbia
| [[United_States_admin_level#Consolidated_city-counties.2C_Independent_cities|New York City]] (unique in USA as an aggl
| [[w:County_(United_States)|state counties and "county equivalents,"]] [[w:County_(United_States)#Territories|territori
| [[w:Civil_township|civil townships]] (in about one-third of states)
| state [[WikiProject United States/Boundaries#municipality|municipality]]: cities, towns, Village and hamlets (infreque
| [[w:Wards_of_the_United_States|wards]] (rare)
| [[WikiProject United States/Boundaries#Municipal subdivisions|neighborhoods]] (infrequent)
|-
| '''{{Flagicon|Uruguay}}'''<br /> <small>''(proposed by [[User:Zeroth|Zeroth]])''</small>
| N/A
| department borders
| N/A
| local board limits (Municipality)
| N/A
| city / town limit
| N/A
| barrios
|-
| '''{{Flagicon|Vanuatu}}'''<br /> <small>''(proposed by [[User:Øukasz|Øukasz]] ([[User talk:Øukasz|talk]]) 00:17, 17 No
| N/A
| Province
| N/A
| Area (sometimes referred to as Area Council. municipality of Port Vila and Luganville are their own Areas)
| N/A
| Ward (subdivision of municipality, and in some cases former municipality)
| Community (Nakamal council) (Not typically used by the central government, but in use to further subdivide some Areas)
| N/A
|-
| '''{{Flagicon|Vietnam}}'''<br /> <small>''(proposed by [[User:ninomax|Ninomax]])<br /> (see also [[wikipedia:vi:Phân c
| N/A
| province border : Tỉnh, thành phố trực thuộc TW
| N/A
| district / township border : quận, huyện, thị xã, thành phố thuộc tỉnh
| N/A
| commune / town / ward border : phường, xã, thị trấn
| N/A
| N/A

"""

eleven_Region = """
|-
| '''{{flagicon|Bolivia}}''' (proposed)
| N/A
| [[wikipedia:es:Department de Bolivia|Department]] / state border
| Regiones / Region
| [[wikipedia:es:Provincias de Bolivia|Provincias]] / province
| Regiones metropolitanas / metropolitan Region
| [[wikipedia:es:Municipality de Bolivia|Municipality]], [[wikipedia:es:Autonomía indígena originario campesina|Territor
| Partes del municipio con autoridad, macrodistricts, comunas, juntas vecinales / parts of the municipality with authori
| Partes del municipio sin autoridad / parts of the municipality without authority
| Organizaciones territoriales de base (OTB), Barrios, [http://blog.upsa.edu.bo/?p=1817 Unidad Vecinal (UV)] / territori
|-
| '''{{flagicon|Germany}}''' see also [[de:Grenze|Grenzen in Deutschland]]
| N/A
| ''federal states border'' Bundesland NUTS 1
| ''state-district border'' Regierungsbezirk NUTS 2
| ''county borders'' Landkreis / Kreis / kreisfreie Stadt NUTS 3
| ''amt'' [http://en.wikipedia.org/wiki/Amt_(political_division)] Samtgemeinde, Verwaltungsgemeinschaft LAU 1 (aka NUTS
| ''Towns, municipality / City-district'' Stadt, Gemeinde LAU 2 (aka NUTS 5)
| '' Parts of a municipality with parish councils /self_government'' Stadtbezirk / Gemeindeteil mit Selbstverwaltung
| '' Parts of a municipality without ...'' Stadtteil / Gemeindeteil ohne Selbstverwaltung
| ''Neighbourhoods'' statistical or historical Stadtviertel etc.
|-
| '''{{flagicon|Mozambique}}''' (proposed)
| N/A
| States (Províncias)
| N/A
| N/A
| N/A
| municipality (Municípios)
| district (districts Municipais)
| Postos Administrativos
| Neighbourhoods (Bairros)
|-
| '''{{flagicon|Netherlands}}''' Updated as proposed in [http://lists.openstreetmap.org/pipermail/talk-nl/2009-May/00899
| border around [http://en.wikipedia.org/wiki/Netherlands The Netherlands], and border around other constituent states i
| province like Zeeland, Noord-Holland etc. ''(provincie)'' NUTS 2 also the [http://en.wikipedia.org/wiki/Caribbean_Neth
| [http://en.wikipedia.org/wiki/Water_board Water board] boundary ''(waterschap)''
| [http://nl.wikipedia.org/wiki/Plusregio ''plusregio''] urban Region in some parts of NL (until 2015-01-01)
| non-official plusregio
| boundary for municipality ''(gemeente)'' (like Amsterdam , Schiermonnikoog) LAU 2 also special municipality (Bonaire,
| boundaries for autonomous city district in Amsterdam ''(stadsdelen)'' en Rotterdam ''(deelgemeenten)''
| boundaries for settlements ''(woonplaatsen)'' (non-autonomous municipal subdivisions)
| boundaries for neighborhoods ''(wijken)''
|-
| '''{{flagicon|Philippines}}'''
| Region (''Rehiyon'')
| province (''Lalawigan'')
| Provincial legislative district
| Cities/municipality (''Lungsod/bayan'')
| City/municipal legislative district
| City/municipal administrative district
| Barangay zones
| Barangay
| Sitio/purok
|-
| '''{{flagicon|Poland}}'''
| N/A
| [[wikipedia:Voivodeships of Poland|''województwa'']] (voivodships, province, Region). [[WikiProject_Poland/Podzia%C5%8
| N/A
| [[wikipedia:Powiat|''powiaty'']] (counties) - some cities have county status - in OSM their borders have both relation
| [[wikipedia:Gmina|''gminy'']] (municipality) - some cities have municipality status - in OSM their borders have both r
| cities, towns and Village. <br />(''miasta, miasteczka i wsie''). [[WikiProject_Poland/Podzia%C5%82_administracyjny#Mi
| City district (''dzielnice'')
| Przysiółki - usually isolated parts of Village. [[WikiProject_Poland/Podzia%C5%82_administracyjny#Przysi.C3.B3.C5.82ki
| boundaries for neighborhoods ''(osiedla)''
|-
| '''{{flagicon|Turkmenistan}}''' ('''''proposed''''')
| N/A
| province / Welayatlar / Области (e.g., Ahal)
| Provincial district / Welayatyň etraplary / Районы областей (e.g., Ak Bugday etrap)
| N/A
| N/A
| Cities and Towns / Şäherler we Şäherçeler / Города и поселки (e.g., Ashgabat, Dashoguz, Ýölöten)
| Rural Councils and Municipal Boroughs with mayors, Village / Geňeşler we Şäheryň häkimli uly etraplary, Obalar / Сельс
| Neighborhoods, Hamlets, Municipal district / Ýaşaýaş toplumlary, Oba ilatly punktlar, Şäheryň kiçi etraplary we etrapç
| Subdistrict / Etrabyň etraplary / Субмикрорайоны (e.g., Parahat 7/2)
"""


class Command(BaseCommand):
    # This is a very quick and dirty script that might skip or break things.
    help = 'Downloads Administrative Region from the OSM wiki and imports them into AdministrativeRegion'

    def handle(self, *args, **options):

        organization_types = dict(OrganizationType.objects.all().values_list('pk', 'name', flat=False))
        matches = []

        # the data in this template is slow.
        # first get everything with 10 Region
        both = ten_Region + eleven_Region
        separate_region_split = both.split("|-")
        for separate_region_split in separate_region_split:
            region_lines = separate_region_split.split("\n")
            country_code = figure_out_country(region_lines)
            if not country_code:
                continue

            # try to get the organization types we know to the rest of the lines. Do not import the very small
            # Region such as cities, parish and other micro scale stuff as the system cannot handle that yet.
            for counter, line in enumerate(region_lines[2:len(region_lines)]):
                for organization_type in organization_types.values():
                    # allow matching on different spaces, spellings and longer layer names etc...
                    if ''.join(ch for ch in organization_type.lower() if ch.isalnum()) in \
                            ''.join(ch for ch in line.lower() if ch.isalnum()):
                        log.debug("Match, administrative region %s is a %s in %s" %
                                  (counter+3, organization_type, country_code))
                        matches.append({'organization_type': organization_type,
                                        'country': country_code,
                                        'admin_level': counter+3})
                        continue

        log.info("Found %s matches." % len(matches))

        import_matches(matches)


def import_matches(matches):

    for match in matches:

        otype = OrganizationType.objects.all().filter(name=match['organization_type']).first()
        if not AdministrativeRegion.objects.all().filter(
                country=match['country'], organization_type=otype, admin_level=match['admin_level']):

            administrative_region = AdministrativeRegion()
            administrative_region.country = match['country']
            administrative_region.admin_level = match['admin_level']
            administrative_region.organization_type = otype
            administrative_region.save()
            log.info("Saved: %s %s = %s" % (
                match['country'], match['organization_type'], match['admin_level']))

        else:
            log.info("Exists already: %s %s = %s" % (
                match['country'], match['organization_type'], match['admin_level']))


def figure_out_country(lines: List[str]):
    country = re.findall('lagicon\|([^}]*)', lines[1], re.MULTILINE)
    if not country:
        # probably a comment line or some sorts
        log.debug("No country found in line %s." % lines[1])
        return
    log.debug(country[0])
    try:
        isocode = countries.get(country[0])
    except KeyError:
        # handle some fallbacks / mismatches here...
        # mismatches with the 3166 library, as the OSM just does things
        # some countries on the OSM list don't exist anymore... oh well :)

        alternatives = {'United Kingdom': 'GB', 'Vietnam': 'VN', 'Bolivia': 'BO',
                        'United States': 'US', 'Tanzania': 'TZ', 'Syria': 'SY',
                        'South Korea': 'KR', 'Russia': 'RU', 'the Philippines': 'PH',
                        'North Korea': 'KP', 'Moldova': 'MD', 'Macedonia': 'MK',
                        'Iran': 'IR', 'Democratic Republic of the Congo': 'CG',
                        'Czech Republic': 'CZ', 'the Central African Republic': 'CF',
                        'Brunei': 'BN'}

        if country[0] in alternatives:
            return alternatives[country[0]]

        log.error("Country %s was not found." % country[0])
        return
    return isocode.alpha2
