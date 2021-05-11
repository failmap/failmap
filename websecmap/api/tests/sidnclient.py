import requests

your_username = "username"
your_password = "password"
your_api_endpoint = "https://[websecmap_instance]/api/SIDN/"

client = requests.session()
client.auth = (your_username, your_password)

print("Get layers")
r = client.get(f"{your_api_endpoint}layers/")
layers = r.json()
print(layers)


print("\nUrls on layers")
r = client.get(f"{your_api_endpoint}2nd_level_urls_on_map/NL/municipality/")
domains = r.json()
print(domains[0:10])


print("\nUpload")
data = {"csrfmiddlewaretoken": client.cookies['csrftoken'], "data": """,2ndlevel,qname,distinct_asns
123,arnhem.nl.,*.arnhem.nl.,1
124,arnhem.nl.,01.arnhem.nl.,1
163,arnhem.nl.,sdfg.arnhem.nl.,1
125,arnhem.nl.,03.arnhem.nl.,1"""}
r = client.post(f"{your_api_endpoint}upload/", data=data)
data = r.json()
print(data)

print("\nReview uploads")
r = client.get(f"{your_api_endpoint}uploads/")
print(r.json())
