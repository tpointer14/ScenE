

// $.get("/instances/1/flow/", function(data){
//     model = 'mymodell'
//     appendDiv(model, 'pm_start', 'Start', ['normal'])
//     buildFlow(data, model);
//     appendDiv(model, 'pm_end', 'end', ['normal'])
// })

// function buildFlow(data, model){
//     for (var key in data) {
//         if(data[key]['key'].startsWith('t')){

//             appendDiv(model, data[key]['key'], data[key]['key'], ['normal'])

//         }else if(data[key]['key'].startsWith('a')){

//             appendDiv(model, data[key]['key'], data[key]['label'], ['normal'])

//         }else if (data[key]['key'].startsWith('loop')){
            
//             appendDiv(model, data[key]['key'], '')
//             appendDiv(data[key]['key'], data[key]['key'] + '_start', 'Start Loop', ['normal'])
//             buildFlow(data[key]['flow'], data[key]['key']); //recursion
//             appendDiv(data[key]['key'], data[key]['key'] + '_end', 'End Loop', ['normal'])

//         }else if (data[key]['key'].startsWith('exclusive')) {

//             appendDiv(model, data[key]['key'], '')
//             appendDiv(data[key]['key'], data[key]['key']+'_start', 'Start_Exclusive', ['normal'])
//             for (var p in data[key]['paths']) {
//                 appendDiv(data[key]['key'], data[key]['key'] + '_' + p, '', ['multiple'])
//                 appendDiv(data[key]['key'] + '_' + p, data[key]['key'] + '_' + p + '_entry_condition', data[key]['paths'][p]['entry_condition'], ['normal'])
//                 buildFlow(data[key]['paths'][p]['flow'], data[key]['key'] + '_' + p);
//             }
//             appendDiv(data[key]['key'], data[key]['key']+'_end', 'End Exclusive', ['normal','multiple_end'])

//         }
//     }
// }

// function appendDiv(element_id, id='', innerHTML='', style_class=''){
//     const pm = document.getElementById(element_id);
//     const div = document.createElement('div');
//     div.id = id;
//     div.innerHTML = innerHTML;
//     if(style_class != ''){
//         div.classList.add(...style_class)
//     }
//     pm.appendChild(div);
//     return true
// }

$(document).on('submit','#createInstance',function(e){
    e.preventDefault();
    $.ajax({
        type:'POST',
        url:'/instances/',
        success: function(data){
            const table = document.getElementById("instances")
            var row = table.insertRow(1);
            row.insertCell(0).innerHTML = data;
            row.insertCell(1).innerHTML = 'description';
            row.insertCell(2).innerHTML = 'whatever';
            row.insertCell(3).innerHTML = '<button type="submit">btn</button>';
        }
    })
});

function buildTable(){
    $.get("/instances/", function(data){
        const table = document.getElementById("instances")
        data.forEach(element => {
            var row = table.insertRow();
            row.insertCell(0).innerHTML = element;
            row.insertCell(1).innerHTML = 'description';
            row.insertCell(2).innerHTML = 'whatever';
            row.insertCell(3).innerHTML = '<button type="submit">btn</button>';
        });
    });

}

buildTable()

// {% for instance in instances %}
// <tr>
//   <td>{{ instance }}</td>
//   <td>{{ instance }}</td>
//   <td><a href="/{{instance}}"><button>Go to</button></a></td>
//   <td></td>
// </tr>
// {% endfor %}