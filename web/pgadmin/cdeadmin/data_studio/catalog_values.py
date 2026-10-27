"""Keep wide native integers exact at the JSON/browser inspection boundary."""


def exact_native_integers(resource):
    native=resource.get('native')
    if not isinstance(native,dict):return
    encodings={}
    def convert(value,path):
        if type(value) is int and abs(value)>2**53-1:
            encodings[path]='native-integer-decimal-text'
            return str(value)
        if isinstance(value,dict):
            return {key:convert(item,path+'/'+str(key).replace('~','~0').replace('/','~1')) for key,item in value.items()}
        if isinstance(value,(list,tuple)):
            return [convert(item,path+'/'+str(index)) for index,item in enumerate(value)]
        return value
    resource['native']=convert(native,'')
    if encodings:resource['native']['json_integer_encodings']=encodings
