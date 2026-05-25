fetch("https://factucloud.up.railway.app/api")
.then(res => res.json())
.then(data => console.log(data));