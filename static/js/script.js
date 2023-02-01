$(document).on('submit','#createInstance',function(e){
    e.preventDefault();
    $.ajax({
        type:'POST',
        url:'/runner/',
        success: function(data){
            const table = document.getElementById("instances")
            var row = table.insertRow(1);
            row.insertCell(0).innerHTML = data;
            row.insertCell(1).innerHTML = '';
            row.insertCell(2).innerHTML = 'ready';
            row.insertCell(3).innerHTML = '<form><button type="submit">Open</button></form>';
        }
    })
});

$(document).on('submit','#startInstance',function(e){
    e.preventDefault();
    $.ajax({
        type:'POST',
        url:'http://192.168.33.10:5000/runner/1/start'
    });
    console.log('hi')
  });

