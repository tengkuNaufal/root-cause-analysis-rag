"""Semantic baseline/runtime settings. No fault catalog or ground-truth lookups."""
import ipaddress
import re

def area(value):
    return str(ipaddress.IPv4Address(int(value) if value.isdigit() else value))

def parse(text):
    settings={};iface=None;bgp=False;route=None;address_family=False
    def put(suffix,value):settings['interface/'+iface+'/'+suffix]=value
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('!'):continue
        if line.startswith('interface '):
            iface=line.split()[1];bgp=False;route=None;continue
        if line.startswith('router '):
            iface=None;route=None;bgp=line.startswith('router bgp ');address_family=False
            if bgp:settings['bgp/asn']=int(line.split()[2])
            continue
        if line.startswith('route-map '):
            parts=line.split();iface=None;bgp=False;route='/'.join(parts[1:4]);settings['route_map/'+route]=[];continue
        if line.startswith('ip prefix-list '):
            iface=None;bgp=False;route=None
            parts=line.split();settings['prefix_list/'+'/'.join(parts[2:5])]=' '.join(parts[5:]);continue
        if line in ('exit','exit-address-family','end'):
            if line=='exit-address-family':address_family=False
            else:iface=None;route=None
            continue
        if iface:
            if line.startswith('ip address '):
                key='interface/'+iface+'/addresses';settings.setdefault(key,[]).append(str(ipaddress.IPv4Interface(line.split()[2])))
            elif line.startswith('ip ospf hello-interval '):put('ospf_hello',int(line.split()[-1]))
            elif line.startswith('ip ospf dead-interval '):put('ospf_dead',int(line.split()[-1]))
            elif line.startswith('ip ospf retransmit-interval '):put('ospf_retransmit',int(line.split()[-1]))
            elif line.startswith('ip ospf area '):put('ospf_area',area(line.split()[-1]))
            elif line.startswith('ip ospf authentication'):
                put('ospf_authentication','message-digest' if 'message-digest' in line else 'simple')
            elif line.startswith('ip ospf message-digest-key '):put('ospf_key_present',True)
        elif route:
            if line.startswith(('match ','set ')):settings['route_map/'+route].append(line)
        elif bgp:
            if line.startswith('address-family '):address_family=True
            elif line.startswith('neighbor '):
                p=line.split();peer=p[1];key='neighbor/'+peer+'/'
                if len(p)>=4 and p[2]=='remote-as':settings[key+'remote_as']=int(p[3])
                elif len(p)>=3 and p[2]=='shutdown':settings[key+'shutdown']=True
                elif len(p)>=5 and p[2]=='route-map':settings[key+'route_map_'+p[4]]=p[3]
                elif len(p)>=3 and p[2]=='activate':settings[key+'activate']=True
                elif len(p)>=4 and p[2]=='update-source':settings[key+'update_source']=p[3]
            elif line.startswith('network '):
                settings.setdefault('bgp/networks',[]).append(str(ipaddress.IPv4Network(line.split()[1])))
    for key in settings:
        if isinstance(settings[key],list):settings[key]=sorted(set(settings[key]))
    return settings

def differences(router,expected,observed):
    output=[]
    defaults={'ospf_authentication':None,'ospf_key_present':False,'shutdown':False}
    inbound_maps={v for source in (expected,observed) for k,v in source.items() if k.endswith('/route_map_in')}
    inbound_lists={line.split()[-1] for source in (expected,observed) for k,v in source.items()
                   if k.startswith('route_map/') and k.split('/')[1] in inbound_maps
                   for line in v if line.startswith('match ip address prefix-list ')}
    for key in sorted(set(expected)|set(observed)):
        default=defaults.get(key.rsplit('/',1)[-1])
        a=expected.get(key,default);b=observed.get(key,default)
        if a==b:continue
        # FRR may omit implicit AF activation on unchanged peers; retain it as context,
        # but a missing activation alone is outside the supported diagnosis vocabulary.
        fact=dict(type='setting',router=router,key=key,expected=a,observed=b,anomaly=True)
        if key.startswith(('neighbor/','bgp/','route_map/','prefix_list/')):
            fact['configuration_context']={'expected_bgp_asn':expected.get('bgp/asn'),'observed_bgp_asn':observed.get('bgp/asn')}
        if key.startswith(('route_map/','prefix_list/')):
            name=key.split('/')[1]
            fact['policy_direction']='inbound' if name in (inbound_maps if key.startswith('route_map/') else inbound_lists) else 'other'
        output.append(fact)
    return output

def supports(cause,fact):
    if fact.get('type')!='setting':return False
    key=fact['key'];a=fact['expected'];b=fact['observed']
    if cause=='ospf_hello_mismatch':return key.endswith('/ospf_hello') and a!=b
    if cause=='ospf_area_mismatch':return key.endswith('/ospf_area') and a!=b
    if cause=='ospf_auth_mismatch':return key.endswith(('/ospf_authentication','/ospf_key_present')) and a!=b
    if cause=='bgp_neighbor_shutdown':return key.startswith('neighbor/') and key.endswith('/shutdown') and b is True
    if cause=='bgp_wrong_remote_as':return key.startswith('neighbor/') and key.endswith('/remote_as') and a is not None and b!=a
    if cause=='bgp_missing_network':return key=='bgp/networks' and bool(set(a or [])-set(b or []))
    if cause=='bgp_inbound_filter':return key.startswith(('route_map/','prefix_list/')) and fact.get('policy_direction')=='inbound' and a!=b
    if cause=='wrong_ip_address':return key.startswith('interface/') and key.endswith('/addresses') and a!=b
    return False
