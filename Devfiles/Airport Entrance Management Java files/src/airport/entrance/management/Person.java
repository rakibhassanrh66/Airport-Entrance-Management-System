package airport.entrance.management;

public class Person {
    private String name;
    private int id;
    // A contact number is not arithmetic. Held as text so leading zeros survive
    // and long numbers do not overflow: 01712345678 does not fit in an int.
    private String num;

    public Person(String name, int id, String num) {
        this.name = name;
        this.id = id;
        this.num = num;
    }

    public String getName() {
        return name;
    }

    public int getId() {
        return id;
    }

    public String getNum() {
        return num;
    }
}
